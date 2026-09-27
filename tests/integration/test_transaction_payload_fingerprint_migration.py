"""Real PostgreSQL proof for durable transaction payload conflict identity."""

from __future__ import annotations

import json
import runpy
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    build_transaction_payload_identity,
    transaction_payload_fingerprint,
)
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_fingerprint_default,
)
from portfolio_common.event_mapping import transaction_event_v1_payload
from portfolio_common.events import TransactionEvent
from sqlalchemy import Integer, String, func, insert, inspect, select, text
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c173b2c3d534_fence_transaction_payload_conflicts.py"
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    migration["upgrade"].__globals__["op"] = Operations(MigrationContext.configure(connection))


@contextmanager
def _rollback_connection(db_engine) -> Iterator[Any]:
    """Keep migration-shape tests isolated from every later database test."""

    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            if transaction.is_active:
                transaction.rollback()


def _event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TX-FINGERPRINT-MIGRATION-001",
        portfolio_id="PORT-FINGERPRINT-MIGRATION-001",
        tenant_id="tenant-fingerprint-a",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 9, 27, 10, 15, tzinfo=UTC),
        settlement_date=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("125.50"),
        gross_transaction_amount=Decimal("1255"),
        trade_currency="USD",
        currency="USD",
        brokerage=Decimal("2.50"),
        source_system="BOOKING_SOURCE",
        source_transaction_reference="BOOKING-001",
    )


def test_transaction_payload_default_supports_orm_multi_values_insert(db_engine) -> None:
    class Base(DeclarativeBase):
        pass

    class TransactionFixture(Base):
        __tablename__ = "transaction_payload_default_fixture"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        transaction_id: Mapped[str] = mapped_column(String, nullable=False)
        portfolio_id: Mapped[str] = mapped_column(String, nullable=False)
        payload_fingerprint: Mapped[str] = mapped_column(
            String,
            nullable=False,
            default=transaction_payload_fingerprint_default,
        )

    payloads = [
        {"transaction_id": "TX-BULK-001", "portfolio_id": "PORT-BULK"},
        {"transaction_id": "TX-BULK-002", "portfolio_id": "PORT-BULK"},
    ]
    Base.metadata.drop_all(db_engine)
    Base.metadata.create_all(db_engine)
    try:
        with _rollback_connection(db_engine) as connection:
            connection.execute(insert(TransactionFixture).values(payloads))
            persisted = list(
                connection.execute(
                    select(TransactionFixture.payload_fingerprint).order_by(TransactionFixture.id)
                ).scalars()
            )
    finally:
        Base.metadata.drop_all(db_engine)

    assert persisted == [transaction_payload_fingerprint(payload) for payload in payloads]


def test_transaction_payload_default_ignores_postgresql_upsert_predicate_binds(
    db_engine,
) -> None:
    class Base(DeclarativeBase):
        pass

    class TransactionFixture(Base):
        __tablename__ = "transaction_payload_upsert_default_fixture"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        transaction_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
        portfolio_id: Mapped[str] = mapped_column(String, nullable=False)
        payload_fingerprint: Mapped[str] = mapped_column(
            String,
            nullable=False,
            default=transaction_payload_fingerprint_default,
        )

    payload = {
        "transaction_id": "TX-UPSERT-PREDICATE-001",
        "portfolio_id": "PORT-UPSERT-PREDICATE",
    }
    Base.metadata.drop_all(db_engine)
    Base.metadata.create_all(db_engine)
    try:
        with _rollback_connection(db_engine) as connection:
            statement = pg_insert(TransactionFixture).values(**payload)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[TransactionFixture.transaction_id],
                    set_={"portfolio_id": statement.excluded.portfolio_id},
                    where=(func.trim(TransactionFixture.portfolio_id) == "PORT-UPSERT-PREDICATE"),
                )
            )
            persisted = connection.execute(
                select(TransactionFixture.payload_fingerprint)
            ).scalar_one()
    finally:
        Base.metadata.drop_all(db_engine)

    assert persisted == transaction_payload_fingerprint(payload)


def _insert_source_outbox(
    connection,
    event: TransactionEvent,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO outbox_events (
                aggregate_type, aggregate_id, partition_key, event_type,
                payload, topic, status, retry_count, created_at
            ) VALUES (
                'RawTransaction', :portfolio_id, :partition_key,
                'RawTransactionPersisted', CAST(:payload AS JSON),
                'transactions.persisted', 'PROCESSED', 0,
                TIMESTAMPTZ '2026-09-27 10:16:00+00'
            )
            """
        ),
        {
            "portfolio_id": event.portfolio_id,
            "partition_key": f"{event.portfolio_id}|{event.security_id}",
            "payload": json.dumps(payload or transaction_event_v1_payload(event)),
        },
    )


def test_transaction_payload_migration_stages_source_evidence_once_across_batches(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    migration["upgrade"].__globals__["_BATCH_SIZE"] = 1
    events = [
        _event().model_copy(
            update={
                "transaction_id": f"TX-FINGERPRINT-STAGING-{sequence:03d}",
                "source_transaction_reference": f"BOOKING-STAGING-{sequence:03d}",
            }
        )
        for sequence in range(1, 4)
    ]

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()
        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT-STAGING', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT-STAGING', FALSE, 'active'
                )
                """
            ),
            {
                "portfolio_id": events[0].portfolio_id,
                "tenant_id": events[0].tenant_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, settlement_date,
                    trade_fee, source_system, source_transaction_reference,
                    cash_entry_mode
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date, :settlement_date,
                    :trade_fee, :source_system, :source_transaction_reference,
                    'AUTO_GENERATE'
                )
                """
            ),
            [
                {
                    **event.model_dump(mode="python"),
                    "trade_fee": event.trade_fee,
                }
                for event in events
            ],
        )
        for event in events:
            _insert_source_outbox(connection, event)

        statements: list[str] = []

        def capture_statement(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            statements.append(statement)

        sqlalchemy_event.listen(db_engine, "before_cursor_execute", capture_statement)
        try:
            migration["upgrade"]()
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", capture_statement)

        normalized = [" ".join(statement.lower().split()) for statement in statements]
        staged_reads = [
            statement
            for statement in normalized
            if statement.startswith("create temporary table c173_raw_transaction_sources")
        ]
        assert len(staged_reads) == 1
        assert "with raw_source as materialized" in staged_reads[0]
        assert "from outbox_events" in staged_reads[0]
        assert [
            statement for statement in normalized if "from outbox_events" in statement
        ] == staged_reads
        assert any(
            statement.startswith("create index c173_raw_transaction_sources_transaction_id_idx")
            for statement in normalized
        )
        assert "analyze c173_raw_transaction_sources" in normalized
        assert len(
            [
                statement
                for statement in normalized
                if "select id, payload from c173_raw_transaction_sources" in statement
            ]
        ) == len(events)


def test_transaction_payload_migration_backfills_and_refuses_inconsistent_fence(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    assert migration["_MATERIAL_FIELDS"] == TRANSACTION_PAYLOAD_MATERIAL_FIELDS
    event = _event()
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"),
        tenant_id=event.tenant_id or "",
    )

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()

        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT', FALSE, 'active'
                )
                """
            ),
            {
                "portfolio_id": event.portfolio_id,
                "tenant_id": event.tenant_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, settlement_date,
                    trade_fee, source_system, source_transaction_reference,
                    economic_event_id, linked_transaction_group_id,
                    calculation_policy_id, calculation_policy_version,
                    cash_entry_mode
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date, :settlement_date,
                    :trade_fee, :source_system, :source_transaction_reference,
                    'EVT-BUY-PORT-FINGERPRINT-MIGRATION-001-TX-FINGERPRINT-MIGRATION-001',
                    'LTG-BUY-PORT-FINGERPRINT-MIGRATION-001-TX-FINGERPRINT-MIGRATION-001',
                    'BUY_DEFAULT_POLICY', '1.0.0', 'AUTO_GENERATE'
                )
                """
            ),
            {
                **event.model_dump(mode="python"),
                "trade_fee": event.trade_fee,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO transaction_costs (transaction_id, fee_type, amount, currency)
                VALUES (:transaction_id, 'brokerage', :amount, 'USD')
                """
            ),
            # Derived cost processing may replace source fee rows; source identity
            # remains the immutable outbox payload, not this mutable breakdown.
            {"transaction_id": event.transaction_id, "amount": Decimal("3.75")},
        )
        _insert_source_outbox(connection, event)
        _insert_source_outbox(connection, event)
        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, tenant_id,
                    correlation_id, semantic_key, payload_fingerprint
                ) VALUES (
                    :transaction_id, :portfolio_id, 'persistence-transactions', :tenant_id,
                    'corr-migration', NULL, :wrong_fingerprint
                )
                """
            ),
            {
                "transaction_id": event.transaction_id,
                "portfolio_id": event.portfolio_id,
                "tenant_id": event.tenant_id,
                "wrong_fingerprint": "sha256:" + "f" * 64,
            },
        )

        rejected = connection.begin_nested()
        with pytest.raises(RuntimeError, match="inconsistent persistence fences"):
            migration["upgrade"]()
        rejected.rollback()

        connection.execute(
            text(
                "UPDATE processed_events SET payload_fingerprint = NULL "
                "WHERE event_id = :transaction_id"
            ),
            {"transaction_id": event.transaction_id},
        )
        migration["upgrade"]()

        assert (
            connection.scalar(
                text(
                    "SELECT payload_fingerprint FROM transactions "
                    "WHERE transaction_id = :transaction_id"
                ),
                {"transaction_id": event.transaction_id},
            )
            == identity.payload_fingerprint
        )
        fence = connection.execute(
            text(
                "SELECT semantic_key, payload_fingerprint FROM processed_events "
                "WHERE event_id = :transaction_id AND service_name = 'persistence-transactions'"
            ),
            {"transaction_id": event.transaction_id},
        ).one()
        assert tuple(fence) == (identity.semantic_key, identity.payload_fingerprint)

        payload_column = next(
            column
            for column in inspect(connection).get_columns("transactions")
            if column["name"] == "payload_fingerprint"
        )
        assert payload_column["nullable"] is False
        check_names = {
            check["name"] for check in inspect(connection).get_check_constraints("transactions")
        }
        assert "ck_transactions_payload_fingerprint" in check_names

        migration["downgrade"]()
        assert "payload_fingerprint" not in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }
        assert (
            connection.scalar(
                text("SELECT count(*) FROM transactions WHERE transaction_id = :transaction_id"),
                {"transaction_id": event.transaction_id},
            )
            == 1
        )

        migration["upgrade"]()
        assert (
            connection.scalar(
                text(
                    "SELECT payload_fingerprint FROM transactions "
                    "WHERE transaction_id = :transaction_id"
                ),
                {"transaction_id": event.transaction_id},
            )
            == identity.payload_fingerprint
        )


def test_transaction_payload_migration_rejects_missing_immutable_source_evidence(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    event = _event()

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()

        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT', FALSE, 'active'
                )
                """
            ),
            {"portfolio_id": event.portfolio_id, "tenant_id": event.tenant_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date
                )
                """
            ),
            event.model_dump(mode="python"),
        )
        rejected = connection.begin_nested()
        with pytest.raises(RuntimeError, match="requires immutable RawTransactionPersisted"):
            migration["upgrade"]()
        rejected.rollback()

        assert "payload_fingerprint" not in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }
        _insert_source_outbox(connection, event)
        migration["upgrade"]()
        assert "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }


def test_transaction_payload_migration_rejects_conflicting_immutable_source_evidence(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    event = _event()

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()
        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT', FALSE, 'active'
                )
                """
            ),
            {"portfolio_id": event.portfolio_id, "tenant_id": event.tenant_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, trade_fee
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date, :trade_fee
                )
                """
            ),
            {**event.model_dump(mode="python"), "trade_fee": event.trade_fee},
        )
        _insert_source_outbox(connection, event)
        conflicting_evidence = connection.begin_nested()
        changed_payload = transaction_event_v1_payload(event)
        changed_payload["quantity"] = "11"
        _insert_source_outbox(connection, event, payload=changed_payload)

        with pytest.raises(RuntimeError, match="conflicting immutable source evidence"):
            migration["upgrade"]()
        conflicting_evidence.rollback()

        migration["upgrade"]()
        assert "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }


def test_transaction_payload_migration_preserves_explicit_zero_named_fee_identity(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    event = _event().model_copy(
        update={
            "brokerage": Decimal(0),
            "trade_fee": Decimal(0),
        }
    )
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"),
        tenant_id=event.tenant_id or "",
    )

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()
        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT', FALSE, 'active'
                )
                """
            ),
            {"portfolio_id": event.portfolio_id, "tenant_id": event.tenant_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, trade_fee
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date, :trade_fee
                )
                """
            ),
            {**event.model_dump(mode="python"), "trade_fee": event.trade_fee},
        )
        _insert_source_outbox(connection, event)

        migration["upgrade"]()

        assert (
            connection.scalar(
                text(
                    "SELECT payload_fingerprint FROM transactions "
                    "WHERE transaction_id = :transaction_id"
                ),
                {"transaction_id": event.transaction_id},
            )
            == identity.payload_fingerprint
        )


def test_transaction_payload_migration_uses_generated_child_row_authority(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    event = _event().model_copy(
        update={
            "transaction_id": "TX-GENERATED-SOURCE-001-CASHLEG",
            "instrument_id": "CASH-USD",
            "security_id": "CASH-USD",
            "transaction_type": "ADJUSTMENT",
            "quantity": Decimal(0),
            "price": Decimal(1),
            "gross_transaction_amount": Decimal("1255"),
            "trade_fee": Decimal(0),
            "brokerage": None,
            "source_system": None,
            "source_transaction_reference": None,
            "cash_entry_mode": "AUTO_GENERATE",
            "originating_transaction_id": "TX-GENERATED-SOURCE-001",
            "originating_transaction_type": "BUY",
            "link_type": "BUY_TO_CASH",
        }
    )
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"),
        tenant_id=event.tenant_id or "",
    )

    with _rollback_connection(db_engine) as connection:
        _bind_operations(migration, connection)
        if "payload_fingerprint" in {
            column["name"] for column in inspect(connection).get_columns("transactions")
        }:
            migration["downgrade"]()
        connection.execute(
            text(
                """
                INSERT INTO portfolios (
                    portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                    risk_exposure, investment_time_horizon, portfolio_type,
                    booking_center_code, client_id, is_leverage_allowed, status
                ) VALUES (
                    :portfolio_id, :tenant_id, 'BOOK-FINGERPRINT', 'USD', DATE '2026-01-01',
                    'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
                    'CLIENT-FINGERPRINT', FALSE, 'active'
                )
                """
            ),
            {"portfolio_id": event.portfolio_id, "tenant_id": event.tenant_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, settlement_date,
                    trade_fee, cash_entry_mode, originating_transaction_id,
                    originating_transaction_type, link_type
                ) VALUES (
                    :transaction_id, :portfolio_id, :instrument_id, :security_id,
                    :transaction_type, :quantity, :price, :gross_transaction_amount,
                    :trade_currency, :currency, :transaction_date, :settlement_date,
                    :trade_fee, :cash_entry_mode, :originating_transaction_id,
                    :originating_transaction_type, :link_type
                )
                """
            ),
            event.model_dump(mode="python"),
        )

        migration["upgrade"]()

        assert (
            connection.scalar(
                text(
                    "SELECT payload_fingerprint FROM transactions "
                    "WHERE transaction_id = :transaction_id"
                ),
                {"transaction_id": event.transaction_id},
            )
            == identity.payload_fingerprint
        )
