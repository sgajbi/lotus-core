"""Verify live position-history repository queries against PostgreSQL."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    FxRate,
    OutboxEvent,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    ProcessedEvent,
    Transaction,
    TransactionCost,
)
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository, SemanticEventClaimOutcome
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_INVALID,
    ReprocessingReplayError,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionCashflowUseCase,
    ReplayBookedTransactionCommand,
    TransactionProcessingIntent,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.application.errors import (
    TransactionProcessingRejected,
)
from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.application.transaction_tenant_authority import (  # noqa: E501
    TransactionTenantAuthorityMismatch,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka.transaction_processing_consumer import (  # noqa: E501
    _message_event_id,
    _message_processing_intent,
    _message_repair_delivery_id,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.history import (
    build_position_history,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.semantic_identity import (  # noqa: E501
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    SqlAlchemyCashflowProcessingState,
    SqlAlchemyCashflowRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisTransactionRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.processing_adapter import (  # noqa: E501
    CostBasisProcessingAdapter,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.observability import (  # noqa: E501
    PrometheusPositionHistoryObserver,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.processing import (  # noqa: E501
    PositionHistoryProcessingAdapter,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.recalculation_state import (  # noqa: E501
    SqlAlchemyPositionRecalculationStateStore,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay.booked_transaction import (  # noqa: E501
    SqlAlchemyQualifiedTransactionReplayReader,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_tenant_authority import (  # noqa: E501
    SqlAlchemyTransactionTenantAuthority,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    PositionMaterializationProgress,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_replay_booked_transaction_use_case,
)
from tests.test_support.async_task_coordination import cancel_pending_tasks, wait_for_task_signal
from tests.test_support.tenant import TEST_TENANT_ID
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    persist_and_process_booked_transaction,
    portfolio_record,
    process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

PORTFOLIO_ID = "POSITION_HISTORY_REPOSITORY_01"
SECURITY_ID = "SEC_POSITION_HISTORY_01"


@pytest.fixture(scope="function")
def position_history_repository_data(db_engine) -> None:
    """Seed independently versioned snapshot and history epochs."""
    with Session(db_engine) as session:
        portfolio = Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )

        session.add(portfolio)
        session.flush()
        session.add_all(
            [
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 1),
                    epoch=0,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 5),
                    epoch=0,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
                DailyPositionSnapshot(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    date=date(2025, 8, 10),
                    epoch=1,
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                ),
            ]
        )
        transactions = [
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E0_A",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 1),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E0_B",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 6),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TX_POSITION_HISTORY_E1_A",
                portfolio_id=PORTFOLIO_ID,
                instrument_id=SECURITY_ID,
                security_id=SECURITY_ID,
                transaction_date=date(2025, 8, 9),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
        ]
        sources = [
            booked_transaction_event(
                transaction_id=row.transaction_id,
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                transaction_date=datetime.combine(
                    row.transaction_date, datetime.min.time(), tzinfo=UTC
                ),
                transaction_type="BUY",
                quantity="1",
                price="1",
                gross_amount="1",
                **(
                    {"trade_fee": "2", "brokerage": Decimal("1.25"), "stamp_duty": Decimal("0.75")}
                    if row.transaction_id == "TX_POSITION_HISTORY_E0_B"
                    else {}
                ),
            )
            for row in transactions
        ]
        session.add_all([canonical_transaction_record(source) for source in sources])
        session.add_all(
            [
                OutboxEvent(
                    aggregate_type="RawTransaction",
                    aggregate_id=PORTFOLIO_ID,
                    event_type="RawTransactionPersisted",
                    topic="raw_transactions",
                    payload=source.model_dump(mode="json"),
                    status="PROCESSED",
                )
                for source in sources
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E0_A",
                    position_date=date(2025, 8, 1),
                    quantity=Decimal("1"),
                    cost_basis=Decimal("1"),
                    epoch=0,
                ),
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E0_B",
                    position_date=date(2025, 8, 6),
                    quantity=Decimal("2"),
                    cost_basis=Decimal("2"),
                    epoch=0,
                ),
                PositionHistory(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    transaction_id="TX_POSITION_HISTORY_E1_A",
                    position_date=date(2025, 8, 9),
                    quantity=Decimal("3"),
                    cost_basis=Decimal("3"),
                    epoch=1,
                ),
            ]
        )
        session.commit()


async def test_materialization_progress_is_epoch_scoped(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
) -> None:
    del clean_db, position_history_repository_data
    repository = SqlAlchemyPositionHistoryRepository(async_db_session)

    assert await repository.load_materialization_progress(
        portfolio_id=f" {PORTFOLIO_ID} ", security_id=f" {SECURITY_ID} ", epoch=0
    ) == PositionMaterializationProgress(
        latest_history_date=date(2025, 8, 6),
        latest_completed_snapshot_date=date(2025, 8, 5),
    )
    assert await repository.load_materialization_progress(
        portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=1
    ) == PositionMaterializationProgress(
        latest_history_date=date(2025, 8, 9),
        latest_completed_snapshot_date=date(2025, 8, 10),
    )
    assert await repository.load_materialization_progress(
        portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=2
    ) == PositionMaterializationProgress(
        latest_history_date=None,
        latest_completed_snapshot_date=None,
    )


async def _stage_replay_window_fee_authority(session: AsyncSession, authority: str) -> None:
    """Bind a genuine corrected cut to committed receipts, not to raw absence alone."""
    raw = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == "RawTransactionPersisted",
            OutboxEvent.payload["transaction_id"].as_string() == "TX_POSITION_HISTORY_E0_B",
        )
    )
    original = TransactionEvent.model_validate(raw.payload)
    original_hash = build_transaction_payload_identity(
        original.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    ).payload_fingerprint
    assert (
        await session.scalar(
            select(Transaction.payload_fingerprint).where(
                Transaction.transaction_id == original.transaction_id
            )
        )
        == original_hash
    )
    assert original.epoch is None  # The stored transaction has no event epoch field.
    corrected = original.model_copy(update={"transaction_date": datetime(2025, 8, 7, tzinfo=UTC)})
    corrected_hash = build_transaction_payload_identity(
        corrected.model_dump(mode="python"), tenant_id=TEST_TENANT_ID
    ).payload_fingerprint
    assert corrected_hash != original_hash
    await session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == original.transaction_id)
        .values(transaction_date=corrected.transaction_date)
    )
    ordinary = build_transaction_semantic_identity(
        map_transaction_event(original, event_id="identity").transaction
    )
    correction = build_transaction_correction_identity(
        map_transaction_event(corrected, event_id="identity").transaction
    )
    assert f":{PORTFOLIO_ID}:{original.transaction_id}:0:sha256:" in correction.semantic_key
    writer = IdempotencyRepository(session)
    identities = [ordinary] if authority == "missing-correction" else [ordinary, correction]
    for index, identity in enumerate(identities):
        assert (
            await writer.claim_semantic_event_processing(
                event_id=f"window-fee-{authority}-{index}",
                portfolio_id=PORTFOLIO_ID,
                service_name="portfolio-transaction-processing",
                semantic_key=identity.semantic_key,
                payload_fingerprint=identity.payload_fingerprint,
                tenant_id=TEST_TENANT_ID,
            )
            is SemanticEventClaimOutcome.CLAIMED
        )
    if authority == "conflicting-original":
        # Valid fallback receipts cannot authorize a raw source contradicting the original hash.
        raw.payload = corrected.model_dump(mode="json")
    else:
        await session.delete(raw)


async def _replay_window_authority_cut(session: AsyncSession) -> list[list[dict]]:
    """Capture independent persisted authority before and after the read/rollback."""
    return [
        [
            dict(row)
            for row in (
                await session.execute(select(model.__table__).order_by(model.id))
            ).mappings()
        ]
        for model in (Transaction, TransactionCost, OutboxEvent, ProcessedEvent)
    ]


@pytest.mark.parametrize(
    "authority", ["original", "correction", "missing-correction", "conflicting-original"]
)
@pytest.mark.parametrize("row_count", [2, 5])
async def test_replay_window_loads_exact_anchor_and_ordered_transactions_once(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
    row_count: int,
    authority: str,
) -> None:
    del clean_db, position_history_repository_data
    original_hash = await async_db_session.scalar(
        select(Transaction.payload_fingerprint).where(
            Transaction.transaction_id == "TX_POSITION_HISTORY_E0_B"
        )
    )
    additional_ids = []
    for index in range(row_count - 2):
        source = booked_transaction_event(
            transaction_id=f"TX_POSITION_HISTORY_Z_EXTRA_{index}",
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            transaction_date=datetime(2025, 8, 9, tzinfo=UTC),
            transaction_type="BUY",
            quantity="1",
            price="1",
            gross_amount="1",
        )
        additional_ids.append(source.transaction_id)
        async_db_session.add(canonical_transaction_record(source))
        async_db_session.add(
            OutboxEvent(
                aggregate_type="RawTransaction",
                aggregate_id=PORTFOLIO_ID,
                event_type="RawTransactionPersisted",
                topic="raw_transactions",
                payload=source.model_dump(mode="json"),
                status="PROCESSED",
            )
        )
    await async_db_session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == "TX_POSITION_HISTORY_E0_B")
        .values(trade_fee=Decimal("99"))
    )
    if authority != "original":
        await _stage_replay_window_fee_authority(async_db_session, authority)
    await async_db_session.commit()
    before = await _replay_window_authority_cut(async_db_session)
    repository = SqlAlchemyPositionHistoryRepository(async_db_session)
    statements: list[str] = []
    receipt_parameters: list[tuple[str, object]] = []

    def capture_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.split()))
        if "FROM processed_events" in statement:
            receipt_parameters.append((statement, _parameters))

    sync_engine = async_db_session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        arguments = dict(
            portfolio_id=f" {PORTFOLIO_ID} ",
            security_id=f" {SECURITY_ID} ",
            position_date=date(2025, 8, 6),
            epoch=0,
        )
        if authority in {"missing-correction", "conflicting-original"}:
            with pytest.raises(ReprocessingReplayError) as rejected:
                await repository.load_replay_window(**arguments)
            assert rejected.value.reason_code == TRANSACTION_REPLAY_SOURCE_INVALID
            assert rejected.value.failed_transaction_ids == ["TX_POSITION_HISTORY_E0_B"]
            assert rejected.value.published_record_count == 0
            window = None
        else:
            window = await repository.load_replay_window(**arguments)
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", capture_statement)

    # Original authority needs no receipt query; genuine absence adds two scoped batches.
    pending = authority in {"correction", "missing-correction"}
    assert len(statements) == (5 if pending else 3)
    assert sum("transactions.transaction_date >=" in sql for sql in statements) == 1
    for authority_table in ("transaction_costs", "outbox_events"):
        assert sum(f"FROM {authority_table}" in sql for sql in statements) == 1
        assert any(f"FOR SHARE OF {authority_table}" in sql for sql in statements)
    assert len(receipt_parameters) == (2 if pending else 0)
    for sql, parameters in receipt_parameters:
        assert "FOR SHARE OF processed_events" in sql
        values = list(parameters.values()) if isinstance(parameters, dict) else list(parameters)
        assert TEST_TENANT_ID in values
        assert PORTFOLIO_ID in values
        assert "portfolio-transaction-processing" in values
        keys = [
            value for value in values if isinstance(value, str) and value.startswith("transaction-")
        ]
        assert keys
        assert all(f":{PORTFOLIO_ID}:TX_POSITION_HISTORY_E0_B:" in key for key in keys)
        assert not any("%" in key for key in keys)
    if pending:
        parameters = receipt_parameters[-1][1]
        values = parameters.values() if isinstance(parameters, dict) else parameters
        correction_keys = [
            value
            for value in values
            if isinstance(value, str) and value.startswith("transaction-correction:")
        ]
        assert correction_keys
        assert all(":0:sha256:" in key for key in correction_keys)
    assert not any("LIKE" in sql.upper() for sql in statements)
    await async_db_session.rollback()
    assert await _replay_window_authority_cut(async_db_session) == before
    if window is None:
        return
    assert window.anchor is not None
    assert window.anchor.transaction_id == "TX_POSITION_HISTORY_E0_A"
    assert window.anchor.epoch == 0
    assert tuple(item.transaction_id for item in window.transactions) == (
        "TX_POSITION_HISTORY_E0_B",
        "TX_POSITION_HISTORY_E1_A",
        *additional_ids,
    )
    assert len(window.transactions) == row_count
    projected = window.transactions[0]
    assert projected.tenant_id == TEST_TENANT_ID
    assert projected.trade_fee == Decimal("2")
    assert projected.brokerage == Decimal("1.25")
    assert projected.stamp_duty == Decimal("0.75")
    assert projected.economic_event_id
    assert projected.linked_transaction_group_id
    assert projected.transaction_date == datetime(
        2025, 8, 6 if authority == "original" else 7, tzinfo=UTC
    )
    assert "transactions.transaction_date >=" in statements[0]
    stored = await async_db_session.scalar(
        select(Transaction).where(Transaction.transaction_id == "TX_POSITION_HISTORY_E0_B")
    )
    assert stored.trade_fee == Decimal("99")
    assert stored.payload_fingerprint == original_hash


@pytest.mark.lifecycle
@pytest.mark.parametrize("upstream_ids", [False, True])
async def test_derived_history_uses_actual_avco_and_preserves_source_identity(
    clean_db, async_db_session: AsyncSession, upstream_ids: bool
) -> None:
    del clean_db
    session = async_db_session
    portfolio_id, security_id = "DERIVED-AVCO-PG", "DERIVED-AVCO-SEC"
    session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="AVCO"),
            instrument_record(
                security_id, name="Derived projection proof", isin="SGDERIVEDAVCO", currency="USD"
            ),
        ]
    )
    await session.commit()
    event = booked_transaction_event(
        transaction_id="DERIVED-SELL",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_type="SELL",
        transaction_date=datetime(2026, 3, 11, tzinfo=UTC),
        quantity="2",
        price="10",
        gross_amount="20",
        **(
            {"economic_event_id": "upstream-event", "linked_transaction_group_id": "upstream-group"}
            if upstream_ids
            else {}
        ),
    )
    await TransactionDBRepository(session).create_or_update_transaction(event)
    await session.commit()
    original_hash = await session.scalar(
        select(Transaction.payload_fingerprint).where(
            Transaction.transaction_id == event.transaction_id
        )
    )
    assert original_hash
    repository = SqlAlchemyPositionHistoryRepository(session)
    full = await repository.list_all_transactions(
        portfolio_id=portfolio_id, security_id=security_id
    )
    window = await repository.load_replay_window(
        portfolio_id=portfolio_id, security_id=security_id, position_date=date(2026, 3, 11), epoch=0
    )
    assert full == window.transactions
    assert window.anchor is None
    projected = full[0]
    assert projected.calculation_policy_id == "SELL_AVCO_POLICY"
    assert projected.epoch is None
    assert projected.brokerage is None
    assert projected.economic_event_id == (
        "upstream-event" if upstream_ids else f"EVT-SELL-{portfolio_id}-DERIVED-SELL"
    )
    assert projected.linked_transaction_group_id == (
        "upstream-group" if upstream_ids else f"LTG-SELL-{portfolio_id}-DERIVED-SELL"
    )
    assert (
        await SqlAlchemyCostBasisTransactionRepository(session).get_derived_financial_transaction(
            projected
        )
        == projected
    )
    row = (
        await session.scalars(
            select(Transaction).where(Transaction.transaction_id == event.transaction_id)
        )
    ).one()
    assert row.payload_fingerprint == original_hash
    assert row.economic_event_id == ("upstream-event" if upstream_ids else None)
    assert row.linked_transaction_group_id == ("upstream-group" if upstream_ids else None)
    # Current PostgreSQL rejects missing hashes before repository admission. The
    # exact-lookup unit control separately covers an unqualified legacy ORM row.
    for missing_hash in (None, ""):
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                row.payload_fingerprint = missing_hash
                await session.flush()
        await session.refresh(row)
        assert row.payload_fingerprint == original_hash
    await session.rollback()


@pytest.mark.lifecycle
@pytest.mark.parametrize("target", ["cashflow", "receipt"])
@pytest.mark.parametrize("release", ["commit", "rollback"])
async def test_materialized_cashflow_holds_actual_updater_until_uow_ends(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
    target: str,
    release: str,
) -> None:
    del clean_db, position_history_repository_data
    cashflow = CalculatedCashflow(
        transaction_id="TX_POSITION_HISTORY_E0_B",
        portfolio_id=PORTFOLIO_ID,
        security_id=SECURITY_ID,
        cashflow_date=date(2025, 8, 6),
        amount=Decimal("-2"),
        currency="USD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=None,
        linked_transaction_group_id=None,
        epoch=0,
    )
    values = asdict(cashflow)
    values.pop("calculation_lineage")
    async_db_session.add_all(
        [
            Cashflow(**values),
            ProcessedEvent(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=PORTFOLIO_ID,
                service_name="cashflow-calculator",
                event_id="cashflow-lock-proof",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    updater_started = asyncio.Event()
    updater_pid = []

    async def update_locked_row():
        async with context.session_factory() as updater:
            async with updater.begin():
                updater_pid.append(await updater.scalar(text("SELECT pg_backend_pid()")))
                updater_started.set()
                if target == "cashflow":
                    statement = (
                        update(Cashflow)
                        .where(
                            Cashflow.transaction_id == cashflow.transaction_id,
                            Cashflow.epoch == 0,
                        )
                        .values(amount=Decimal("-3"))
                    )
                else:
                    statement = (
                        update(ProcessedEvent)
                        .where(
                            ProcessedEvent.tenant_id == TEST_TENANT_ID,
                            ProcessedEvent.portfolio_id == PORTFOLIO_ID,
                            ProcessedEvent.service_name == "cashflow-calculator",
                            ProcessedEvent.event_id == "cashflow-lock-proof",
                        )
                        .values(correlation_id="changed")
                    )
                result = await updater.execute(statement)
                assert result.rowcount == 1

    async with context.session_factory() as holder:
        await holder.begin()
        holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
        retained = await SqlAlchemyCashflowRepository(holder).load_materialized(
            cashflow, tenant_id=TEST_TENANT_ID, semantic_event_id="cashflow-lock-proof"
        )
        assert retained is not None
        assert retained.amount == cashflow.amount
        contender = asyncio.create_task(update_locked_row())
        try:
            await wait_for_task_signal(contender, updater_started, timeout=5)
            async with asyncio.timeout(5):
                while True:
                    if contender.done():
                        await contender
                        pytest.fail("updater completed while cashflow authority locks were held")
                    async with context.session_factory() as observer:
                        blockers = await observer.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": updater_pid[0]}
                        )
                    if holder_pid in blockers:
                        break
                    await asyncio.sleep(0.01)
            assert not contender.done()
            if release == "commit":
                await holder.commit()
            else:
                await holder.rollback()
            await asyncio.wait_for(contender, timeout=5)
        finally:
            await holder.rollback()
            await cancel_pending_tasks(contender)


@pytest.mark.lifecycle
@pytest.mark.parametrize("target", ["portfolio", "state", "history"])
@pytest.mark.parametrize("release", ["commit", "rollback"])
async def test_materialized_position_receipt_holds_actual_updater_until_uow_ends(
    clean_db,
    position_history_repository_data: None,
    async_db_session: AsyncSession,
    target: str,
    release: str,
) -> None:
    del clean_db, position_history_repository_data
    async_db_session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=0,
            watermark_date=date(2025, 8, 9),
        )
    )
    await async_db_session.commit()
    transaction = map_transaction_event(
        booked_transaction_event(
            transaction_id="TX_POSITION_HISTORY_E0_B",
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            transaction_type="BUY",
            transaction_date=datetime(2025, 8, 6, tzinfo=UTC),
            quantity="1",
            price="1",
            gross_amount="1",
        ),
        event_id="lock-proof",
        correlation_id="lock-proof",
    ).transaction
    context = transaction_processing_test_context(async_db_session)
    updater_started = asyncio.Event()
    updater_pid = []

    async def update_locked_row():
        async with context.session_factory() as updater:
            async with updater.begin():
                updater_pid.append(await updater.scalar(text("SELECT pg_backend_pid()")))
                updater_started.set()
                if target == "portfolio":
                    statement = (
                        update(Portfolio)
                        .where(Portfolio.portfolio_id == PORTFOLIO_ID)
                        .values(risk_exposure="changed")
                    )
                elif target == "state":
                    statement = (
                        update(PositionState)
                        .where(
                            PositionState.portfolio_id == PORTFOLIO_ID,
                            PositionState.security_id == SECURITY_ID,
                        )
                        .values(epoch=1)
                    )
                else:
                    statement = (
                        update(PositionHistory)
                        .where(
                            PositionHistory.transaction_id == "TX_POSITION_HISTORY_E0_B",
                            PositionHistory.epoch == 0,
                        )
                        .values(quantity=Decimal("3"))
                    )
                result = await updater.execute(statement)
                assert result.rowcount == 1

    async with context.session_factory() as holder:
        await holder.begin()
        holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
        receipt = await SqlAlchemyPositionHistoryRepository(holder).load_materialized_receipt(
            transaction, expected_epoch=0
        )
        assert receipt is not None
        assert receipt.quantity == Decimal("2")
        contender = asyncio.create_task(update_locked_row())
        try:
            await wait_for_task_signal(contender, updater_started, timeout=5)
            async with asyncio.timeout(5):
                while True:
                    if contender.done():
                        await contender
                        pytest.fail("updater completed while materialization locks were held")
                    async with context.session_factory() as observer:
                        blockers = await observer.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": updater_pid[0]}
                        )
                    if holder_pid in blockers:
                        break
                    await asyncio.sleep(0.01)
            assert not contender.done()
            if release == "commit":
                await holder.commit()
            else:
                await holder.rollback()
            await asyncio.wait_for(contender, timeout=5)
        finally:
            await holder.rollback()
            await cancel_pending_tasks(contender)


@pytest.mark.lifecycle
@pytest.mark.parametrize("component", ["FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"])
async def test_declared_no_cash_stage_retains_only_committed_scoped_receipt(
    clean_db, async_db_session: AsyncSession, component: str
) -> None:
    del clean_db
    portfolio_id = "NO-CASH-EFFECT-PG"
    session = async_db_session
    session.add(portfolio_record(portfolio_id))
    session.add(
        Transaction(
            transaction_id="NO-CASH",
            portfolio_id=portfolio_id,
            security_id="FX-CONTRACT",
            instrument_id="FX-CONTRACT",
            transaction_type="FX_FORWARD",
            component_type=component,
            transaction_date=datetime(2026, 3, 11, tzinfo=UTC),
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            currency="USD",
            trade_currency="USD",
            trade_fee=Decimal("0"),
        )
    )
    await session.commit()
    transaction = BookedTransaction(
        transaction_id="NO-CASH",
        portfolio_id=portfolio_id,
        security_id="FX-CONTRACT",
        instrument_id="FX-CONTRACT",
        tenant_id=TEST_TENANT_ID,
        transaction_type="FX_FORWARD",
        component_type=component,
        transaction_date=datetime(2026, 3, 11, tzinfo=UTC),
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        currency="USD",
        trade_currency="USD",
        trade_fee=Decimal("0"),
        epoch=1,
    )
    context = transaction_processing_test_context(session)

    def cashflow_use_case(active_session):
        return ProcessTransactionCashflowUseCase(
            rules=AsyncMock(),
            events=AsyncMock(),
            observer=AsyncMock(),
            state=SqlAlchemyCashflowProcessingState(
                active_session, IdempotencyRepository(active_session), source_topic="proof"
            ),
            persistence=SqlAlchemyCashflowRepository(active_session),
        )

    async with context.session_factory() as producer:
        async with producer.begin():
            outcome = await cashflow_use_case(producer).process(
                transaction,
                event_id="no-cash-first",
                correlation_id="proof",
                traceparent=None,
                locked_position_epoch=1,
            )
            assert outcome.cashflow_record_count == 0
    async with context.session_factory() as qualification:
        async with qualification.begin():
            use_case = cashflow_use_case(qualification)
            assert await use_case.has_materialized_effect(transaction, locked_position_epoch=1)
            for changed in (
                replace(transaction, tenant_id="foreign"),
                replace(transaction, portfolio_id="foreign"),
                replace(transaction, transaction_id="foreign"),
                replace(transaction, epoch=2),
            ):
                assert not await use_case.has_materialized_effect(
                    changed, locked_position_epoch=changed.epoch
                )
            assert await qualification.scalar(select(func.count(Cashflow.id))) == 0
            assert await qualification.scalar(select(func.count(ProcessedEvent.id))) == 1
    # A rolled-back semantic stage supplies no completed no-effect authority.
    uncommitted = replace(transaction, transaction_id="ROLLED-BACK")
    async with context.session_factory() as rollback:
        await rollback.begin()
        await cashflow_use_case(rollback).process(
            uncommitted,
            event_id="no-cash-rollback",
            correlation_id="proof",
            traceparent=None,
            locked_position_epoch=1,
        )
        await rollback.rollback()
    async with context.session_factory() as verification:
        assert not await cashflow_use_case(verification).has_materialized_effect(
            uncommitted, locked_position_epoch=1
        )
        assert await verification.scalar(select(func.count(Cashflow.id))) == 0
        assert await verification.scalar(select(func.count(ProcessedEvent.id))) == 1
        # Even a zero-valued ledger contradicts declared no-effect evidence.
        verification.add(
            Cashflow(
                transaction_id=transaction.transaction_id,
                portfolio_id=portfolio_id,
                security_id=transaction.security_id,
                epoch=1,
                cashflow_date=date(2026, 3, 11),
                amount=Decimal("0"),
                currency="USD",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                calculation_type="NET",
                is_position_flow=True,
                is_portfolio_flow=False,
            )
        )
        await verification.flush()
        assert not await cashflow_use_case(verification).has_materialized_effect(
            transaction, locked_position_epoch=1
        )
        await verification.rollback()


@pytest.mark.lifecycle
async def test_funded_cash_book_suffix_replay_preserves_cashflow_history_epochs_and_rollback(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Exercise the producer seam without treating a passing hypothesis as live diagnosis."""
    portfolio_id = "CASH-HISTORY-COHERENCE-PG"
    cash_security = "CASH-HISTORY-USD"
    product_security = "CASH-HISTORY-EQUITY"
    session = async_db_session
    session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                cash_security,
                name="Funded USD cash book",
                isin="CASH-HISTORY-USD",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            instrument_record(
                product_security,
                name="Paired equity",
                isin="CASH-HISTORY-EQUITY",
                currency="USD",
            ),
        ]
    )
    await session.commit()
    context = transaction_processing_test_context(session)

    def event(transaction_id, security_id, kind, day, quantity, price, gross, pair=None):
        trade = datetime(2026, 1, day, 10, tzinfo=UTC)
        return booked_transaction_event(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=trade,
            transaction_type=kind,
            quantity=quantity,
            price=price,
            gross_amount=gross,
            settlement_date=trade + timedelta(days=2),
            **({"economic_event_id": pair, "linked_transaction_group_id": pair} if pair else {}),
        )

    funded = event("COHERENCE-FUND", cash_security, "DEPOSIT", 1, "1000", "1", "1000")
    purchase = event(
        "COHERENCE-PRODUCT-BUY", product_security, "BUY", 3, "1", "100", "100", "PAIR-BUY"
    )
    payment = event("COHERENCE-CASH-SELL", cash_security, "SELL", 3, "100", "1", "100", "PAIR-BUY")
    sale = event(
        "COHERENCE-PRODUCT-SELL", product_security, "SELL", 4, "0.2", "100", "20", "PAIR-SELL"
    )
    receipt = event("COHERENCE-CASH-BUY", cash_security, "BUY", 4, "20", "1", "20", "PAIR-SELL")
    original_events = (funded, purchase, payment, sale, receipt)
    for index, booked in enumerate(original_events):
        result = await persist_and_process_booked_transaction(
            session=session,
            context=context,
            event=booked,
            event_id=f"cash-history-booking-{index}",
            correlation_id="cash-history-proof",
        )
        assert result.status is TransactionProcessingStatus.PROCESSED

    async def persisted_cut():
        async with context.session_factory() as verification:
            histories = (
                await verification.scalars(
                    select(PositionHistory)
                    .where(PositionHistory.portfolio_id == portfolio_id)
                    .order_by(PositionHistory.epoch, PositionHistory.transaction_id)
                )
            ).all()
            flows = (
                await verification.scalars(
                    select(Cashflow)
                    .where(Cashflow.portfolio_id == portfolio_id)
                    .order_by(Cashflow.epoch, Cashflow.transaction_id)
                )
            ).all()
            sources = (
                await verification.scalars(
                    select(Transaction)
                    .where(Transaction.portfolio_id == portfolio_id)
                    .order_by(Transaction.transaction_id)
                )
            ).all()
            return (
                [
                    (
                        h.transaction_id,
                        h.security_id,
                        h.epoch,
                        h.position_date,
                        h.quantity,
                        h.cost_basis,
                        h.calculation_lineage,
                    )
                    for h in histories
                ],
                [
                    (
                        f.transaction_id,
                        f.security_id,
                        f.epoch,
                        f.cashflow_date,
                        f.amount,
                        f.classification,
                        f.timing,
                        f.calculation_lineage,
                    )
                    for f in flows
                ],
                [
                    (
                        t.transaction_id,
                        t.transaction_date,
                        t.settlement_date,
                        t.quantity,
                        t.gross_transaction_amount,
                    )
                    for t in sources
                ],
            )

    original_cut = await persisted_cut()
    assert len(original_cut[0]) == len(original_cut[1]) == 5
    assert {h[2] for h in original_cut[0]} == {0}
    assert {f[2] for f in original_cut[1]} == {0}
    trade_dates = {
        booked.transaction_id: booked.transaction_date.date() for booked in original_events
    }
    for flow in original_cut[1]:
        history = next(h for h in original_cut[0] if h[:3] == flow[:3])
        assert history[3] == trade_dates[flow[0]]
        assert flow[3] == trade_dates[flow[0]] + timedelta(days=2)
    amounts = {f[0]: f[4] for f in original_cut[1]}
    assert amounts[purchase.transaction_id] == -amounts[payment.transaction_id]
    assert amounts[sale.transaction_id] == -amounts[receipt.transaction_id]
    assert next(h[4] for h in original_cut[0] if h[0] == receipt.transaction_id) == Decimal("920")

    # Exercise the native same-epoch suffix repository/reducer seam explicitly.
    # A delivered older transaction instead advances recovery epoch by policy.
    async with context.session_factory() as replay_session:
        async with replay_session.begin():
            repository = SqlAlchemyPositionHistoryRepository(replay_session)
            await repository.acquire_replay_lock(
                portfolio_id=portfolio_id,
                security_id=cash_security,
                epoch=0,
            )
            deleted = await repository.delete_records_from(
                portfolio_id=portfolio_id,
                security_id=cash_security,
                position_date=payment.transaction_date.date(),
                epoch=0,
            )
            assert deleted == 2
            window = await repository.load_replay_window(
                portfolio_id=portfolio_id,
                security_id=cash_security,
                position_date=payment.transaction_date.date(),
                epoch=0,
            )
            assert window.anchor.transaction_id == funded.transaction_id
            assert {t.transaction_id for t in window.transactions} == {
                payment.transaction_id,
                receipt.transaction_id,
            }
            await repository.save_records(
                build_position_history(
                    anchor=window.anchor,
                    transactions=window.transactions,
                    epoch=0,
                )
            )
    replayed_cut = await persisted_cut()
    assert [h[:6] for h in replayed_cut[0]] == [h[:6] for h in original_cut[0]]
    assert replayed_cut[1:] == original_cut[1:]

    earlier = event("COHERENCE-BACKDATED-FUND", cash_security, "DEPOSIT", 2, "50", "1", "50")
    rebuilt = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=earlier,
        event_id="cash-history-backdated",
        correlation_id="cash-history-proof",
    )
    assert rebuilt.status is TransactionProcessingStatus.PROCESSED
    advanced_cut = await persisted_cut()
    # Epoch0 is immutable retained evidence; epoch1 has an independently coherent cash stream.
    assert [h for h in advanced_cut[0] if h[2] == 0] == replayed_cut[0]
    assert [f for f in advanced_cut[1] if f[2] == 0] == original_cut[1]
    epoch_one_flows = [f for f in advanced_cut[1] if f[2] == 1]
    assert {f[0] for f in epoch_one_flows} == {
        funded.transaction_id,
        payment.transaction_id,
        receipt.transaction_id,
        earlier.transaction_id,
    }
    for flow in epoch_one_flows:
        history = next(h for h in advanced_cut[0] if h[:3] == flow[:3])
        assert history[3] == (
            earlier.transaction_date.date()
            if flow[0] == earlier.transaction_id
            else trade_dates[flow[0]]
        )
        assert flow[3] == history[3] + timedelta(days=2)
        if flow[0] != earlier.transaction_id:
            assert flow[4] == amounts[flow[0]]
    assert next(
        h[4] for h in advanced_cut[0] if h[0] == receipt.transaction_id and h[2] == 1
    ) == Decimal("970")
    assert [s for s in advanced_cut[2] if s[0] != earlier.transaction_id] == original_cut[2]

    staged_statements = []

    def fail_before_commit(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        staged_statements.append(normalized)
        if "select flush_deferred_portfolio_cashflow_source_cuts()" in normalized:
            raise RuntimeError("injected failure after native history and cashflow writes")

    sync_engine = session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", fail_before_commit)
    try:
        with pytest.raises(RuntimeError, match="after native history and cashflow writes"):
            await process_booked_transaction(
                context=context,
                event=receipt.model_copy(update={"epoch": 1}),
                event_id="cash-history-rollback",
                correlation_id="cash-history-proof",
                processing_intent=TransactionProcessingIntent.REPAIR,
                repair_delivery_id="cash-history-rollback",
            )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", fail_before_commit)
    assert any("delete from position_history" in sql for sql in staged_statements)
    assert any("insert into position_history" in sql for sql in staged_statements)
    assert any("insert into cashflows" in sql for sql in staged_statements)
    assert await persisted_cut() == advanced_cut
    async with context.session_factory() as verification:
        assert (
            await verification.scalar(
                select(ProcessedEvent.id).where(ProcessedEvent.event_id == "cash-history-rollback")
            )
            is None
        )


@pytest.mark.lifecycle
async def test_late_unversioned_interest_cash_leg_uses_materialized_history_epoch(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
) -> None:
    """A late ordinary cash leg must not normalize an accepted epoch to zero."""
    portfolio_id = "LATE-INTEREST-CASH-HISTORY-PG"
    security_id = "LATE-INTEREST-USD-CASH"
    session = async_db_session
    session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Interest receipt cash book",
                isin="LATE-INTEREST-CASH",
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
        ]
    )
    await session.commit()
    context = transaction_processing_test_context(session)

    def cash_event(transaction_id, kind, day, amount):
        return booked_transaction_event(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 3, day, 10, tzinfo=UTC),
            settlement_date=datetime(2026, 3, day, 16, tzinfo=UTC),
            transaction_type=kind,
            quantity=amount,
            price="1",
            gross_amount=amount,
        )

    # Native backdated materialization establishes epoch1 without changing a state row by hand.
    for index, booked in enumerate(
        (
            cash_event("LATE-FUND", "DEPOSIT", 8, "1000"),
            cash_event("BACKDATED-FUND", "DEPOSIT", 1, "50"),
        )
    ):
        result = await persist_and_process_booked_transaction(
            session=session,
            context=context,
            event=booked,
            event_id=f"late-interest-fund-{index}",
            correlation_id="late-interest-proof",
        )
        assert result.status is TransactionProcessingStatus.PROCESSED

    cash_leg = cash_event("LATE-CASH-INTEREST", "BUY", 11, "1187").model_copy(
        update={
            "economic_event_id": "PAIRED-UST-INTEREST",
            "linked_transaction_group_id": "PAIRED-UST-INTEREST",
        }
    )
    assert cash_leg.epoch is None
    result = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=cash_leg,
        event_id="late-interest-cash-delivery",
        correlation_id="late-interest-proof",
    )
    assert result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as verification:
        state = await verification.scalar(
            select(PositionState).where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.security_id == security_id,
            )
        )
        histories = (
            await verification.scalars(
                select(PositionHistory).where(
                    PositionHistory.portfolio_id == portfolio_id,
                    PositionHistory.transaction_id == cash_leg.transaction_id,
                )
            )
        ).all()
        flows = (
            await verification.scalars(
                select(Cashflow).where(
                    Cashflow.portfolio_id == portfolio_id,
                    Cashflow.transaction_id == cash_leg.transaction_id,
                )
            )
        ).all()
        source = await verification.scalar(
            select(Transaction).where(
                Transaction.transaction_id == cash_leg.transaction_id,
            )
        )
        assert state.epoch == 1
        assert len(histories) == len(flows) == 1
        assert histories[0].epoch == 1
        assert histories[0].position_date == date(2026, 3, 11)
        assert histories[0].quantity == Decimal("2237")
        assert flows[0].cashflow_date == date(2026, 3, 11)
        assert flows[0].amount == Decimal("-1187")
        assert flows[0].classification == "INVESTMENT_OUTFLOW"
        assert flows[0].is_position_flow and not flows[0].is_portfolio_flow
        assert source.transaction_date == cash_leg.transaction_date
        assert source.settlement_date == cash_leg.settlement_date
        print(
            {
                "event_epoch": cash_leg.epoch,
                "state_epoch": state.epoch,
                "history_epoch": histories[0].epoch,
                "cashflow_epoch": flows[0].epoch,
                "trade_date": histories[0].position_date.isoformat(),
                "ledger_date": flows[0].cashflow_date.isoformat(),
                "cashflow_amount": str(flows[0].amount),
            }
        )
        assert flows[0].epoch == histories[0].epoch, (
            "Accepted late unversioned cash delivery must bind cashflow to its materialized epoch"
        )

    duplicate = await process_booked_transaction(
        context=context,
        event=cash_leg,
        event_id="late-interest-cash-delivery",
        correlation_id="late-interest-proof",
    )
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE
    repair = await process_booked_transaction(
        context=context,
        event=cash_leg,
        event_id="late-interest-repair",
        correlation_id="late-interest-proof",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="late-interest-repair",
    )
    assert repair.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as verification:
        repaired_flows = (
            await verification.scalars(
                select(Cashflow).where(
                    Cashflow.portfolio_id == portfolio_id,
                    Cashflow.transaction_id == cash_leg.transaction_id,
                )
            )
        ).all()
        repaired_histories = (
            await verification.scalars(
                select(PositionHistory).where(
                    PositionHistory.portfolio_id == portfolio_id,
                    PositionHistory.transaction_id == cash_leg.transaction_id,
                )
            )
        ).all()
        assert len(repaired_flows) == len(repaired_histories) == 1
        assert repaired_flows[0].epoch == repaired_histories[0].epoch == 1
        assert repaired_flows[0].amount == Decimal("-1187")
        assert (
            repaired_flows[0].cashflow_date
            == repaired_histories[0].position_date
            == date(2026, 3, 11)
        )

    async def ledger_cut():
        async with context.session_factory() as verification:
            history = (
                await verification.scalars(
                    select(PositionHistory).where(PositionHistory.portfolio_id == portfolio_id)
                )
            ).all()
            flows = (
                await verification.scalars(
                    select(Cashflow).where(Cashflow.portfolio_id == portfolio_id)
                )
            ).all()
            return (
                sorted((row.id, row.transaction_id, row.epoch, row.quantity) for row in history),
                sorted((row.id, row.transaction_id, row.epoch, row.amount) for row in flows),
            )

    async def assert_native_empty(event, *, materialized_quantity=None):
        before = await ledger_cut()
        async with context.session_factory() as native_session:
            async with native_session.begin():
                adapter = PositionHistoryProcessingAdapter(
                    processor=PositionHistoryProcessor(
                        repository=SqlAlchemyPositionHistoryRepository(native_session),
                        state_store=SqlAlchemyPositionRecalculationStateStore(
                            PositionStateRepository(native_session)
                        ),
                        observer=PrometheusPositionHistoryObserver(),
                    )
                )
                result = await adapter.process(
                    map_transaction_event(
                        event, event_id="native-empty-control", correlation_id="late-interest-proof"
                    ).transaction,
                    correlation_id="late-interest-proof",
                    traceparent=None,
                )
                assert result.position_record_count == 0
                if materialized_quantity is None:
                    assert result.locked_state_epoch is None
                    assert result.materialized_receipt is None
                else:
                    assert result.locked_state_epoch == 1
                    assert result.processed_transaction_quantity == materialized_quantity
                    receipt = result.materialized_receipt
                    assert receipt is not None
                    assert receipt.tenant_id == "tenant-test"
                    assert receipt.portfolio_id == portfolio_id
                    assert receipt.security_id == security_id
                    assert receipt.transaction_id == event.transaction_id
                    assert receipt.epoch == 1
                    assert receipt.quantity == materialized_quantity
                assert not result.cashflow_rebuild_transactions
        assert await ledger_cut() == before

    # Actual stale processing returns empty. The combined path retains its old terminal fence,
    # rather than turning this explicit source disposition into a permanent retryable refusal.
    stale = cash_leg.model_copy(update={"epoch": 0})
    await assert_native_empty(stale)
    before_stale = await ledger_cut()
    with pytest.raises(TransactionProcessingRejected) as failure:
        await process_booked_transaction(
            context=context,
            event=stale,
            event_id="late-interest-stale-repair",
            correlation_id="late-interest-proof",
            processing_intent=TransactionProcessingIntent.REPAIR,
            repair_delivery_id="late-interest-stale-repair-intent",
        )
    assert failure.value.reason_code == "cashflow_epoch_rejected"
    assert not failure.value.retryable
    assert await ledger_cut() == before_stale

    backdated = cash_event("BACKDATED-FUND", "DEPOSIT", 1, "50")
    await assert_native_empty(backdated, materialized_quantity=Decimal("50"))
    position_calls = []
    original_process = PositionHistoryProcessingAdapter.process

    async def observed_process(adapter, transaction, **kwargs):
        position_calls.append(transaction.transaction_id)
        return await original_process(adapter, transaction, **kwargs)

    with monkeypatch.context() as probe:
        probe.setattr(PositionHistoryProcessingAdapter, "process", observed_process)
        semantic_duplicate = await process_booked_transaction(
            context=context,
            event=backdated,
            event_id="different-physical-backdated-delivery",
            correlation_id="late-interest-proof",
        )
    assert semantic_duplicate.status is TransactionProcessingStatus.DUPLICATE
    assert not position_calls
    assert await ledger_cut() == before_stale

    # Persistence can precede processing: an authorized replay of another source row can
    # materialize this pending input's history before its ordinary raw claim exists.
    pending = cash_event("PENDING-CASH-RECEIPT", "DEPOSIT", 4, "20")
    session.add(canonical_transaction_record(pending))
    await session.commit()
    replay = await process_booked_transaction(
        context=context,
        event=backdated.model_copy(update={"epoch": 1}),
        event_id="materialize-pending-history",
        correlation_id="late-interest-proof",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="materialize-pending-history-intent",
    )
    assert replay.status is TransactionProcessingStatus.PROCESSED
    await assert_native_empty(pending, materialized_quantity=Decimal("70"))
    before_pending = await ledger_cut()
    assert any(row[1] == pending.transaction_id and row[2] == 1 for row in before_pending[0])
    assert not any(row[1] == pending.transaction_id for row in before_pending[1])
    with pytest.raises(TransactionProcessingRejected) as failure:
        await process_booked_transaction(
            context=context,
            event=pending,
            event_id="unclaimed-pending-ordinary",
            correlation_id="late-interest-proof",
        )
    assert failure.value.reason_code == "position_materialization_unavailable"
    assert await ledger_cut() == before_pending
    # First-claimed canonical REPAIR validates original source before rebuilding the
    # pending transaction; ordinary coalescence above still refuses without effects.
    unversioned_repair = await process_booked_transaction(
        context=context,
        event=pending,
        event_id="unclaimed-pending-unversioned-repair",
        correlation_id="late-interest-proof",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="unclaimed-pending-unversioned-repair-intent",
    )
    assert unversioned_repair.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as verification:
        captured_epoch = await verification.scalar(
            select(PositionState.epoch).where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.security_id == security_id,
            )
        )
    assert captured_epoch == 2
    unversioned_cut = await ledger_cut()
    assert any(
        row[1] == pending.transaction_id and row[2] == captured_epoch and row[3] == Decimal("70")
        for row in unversioned_cut[0]
    )
    assert any(
        row[1] == pending.transaction_id and row[2] == captured_epoch and row[3] == Decimal("20")
        for row in unversioned_cut[1]
    )
    repaired = await process_booked_transaction(
        context=context,
        event=pending.model_copy(update={"epoch": captured_epoch}),
        event_id="unclaimed-pending-supported-repair",
        correlation_id="late-interest-proof",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id="unclaimed-pending-supported-repair-intent",
    )
    assert repaired.status is TransactionProcessingStatus.PROCESSED
    repaired_cut = await ledger_cut()
    assert any(
        row[1] == pending.transaction_id and row[2] == captured_epoch for row in repaired_cut[0]
    )
    assert any(
        row[1] == pending.transaction_id and row[2] == captured_epoch for row in repaired_cut[1]
    )


@pytest.mark.lifecycle
@pytest.mark.parametrize(
    "prior_claimed,enriched_first_claim,named_fees",
    [
        (True, False, None),
        (False, False, None),
        (False, True, None),
        (False, False, "complete"),
        (False, False, "sparse"),
        (False, False, "zero-only"),
        (False, False, "aggregate-only"),
        (True, False, "retained-no-raw"),
        (True, False, "retained-concurrent"),
        (False, False, "deferred"),
        (False, False, "zero-stamp_duty"),
        (False, False, "zero-exchange_fee"),
        (False, False, "zero-gst"),
        (False, False, "zero-other_fees"),
        (True, False, "retained-mixed-zero"),
    ],
    ids=[
        "prior-claimed",
        "unclaimed",
        "unclaimed-cost-enriched",
        "unclaimed-named-fees",
        "unclaimed-sparse-fees",
        "unclaimed-zero-only-fees",
        "unclaimed-aggregate-only-fees",
        "prior-claimed-no-raw",
        "prior-claimed-concurrent-source-receipt",
        "first-claimed-deferred-rollback",
        "first-claimed-component-zero-stamp",
        "first-claimed-component-zero-exchange",
        "first-claimed-component-zero-gst",
        "first-claimed-component-zero-other",
        "prior-claimed-mixed-zero-no-raw",
    ],
)
async def test_canonical_unversioned_repair_materializes_cashflow_history_coherence(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
    prior_claimed: bool,
    enriched_first_claim: bool,
    named_fees: str | None,
) -> None:
    """Canonical replay must recover without an epoch or repair-delivery header."""
    portfolio_id = f"CANONICAL-REPAIR-{prior_claimed}-{enriched_first_claim}-{named_fees}"
    security_id = f"CANONICAL-CASH-{prior_claimed}-{enriched_first_claim}-{named_fees}"
    session = async_db_session
    session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Canonical repair cash book",
                isin=portfolio_id,
                currency="USD",
                product_type="EQUITY" if enriched_first_claim else "CASH",
                asset_class="Equity" if enriched_first_claim else "Cash",
            ),
        ]
    )
    await session.commit()
    context = transaction_processing_test_context(session)

    def cash_event(transaction_id, kind, day, amount):
        return booked_transaction_event(
            transaction_id=f"{portfolio_id}-{transaction_id}",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 3, day, 10, tzinfo=UTC),
            settlement_date=datetime(2026, 3, day, 16, tzinfo=UTC),
            transaction_type=kind,
            quantity=amount,
            price="1",
            gross_amount=amount,
        )

    target = cash_event("INTEREST-CASH", "BUY", 11 if prior_claimed else 4, "1187")
    if (named_fees or "").startswith("zero-") and named_fees != "zero-only":
        target = TransactionEvent.model_validate(
            target.model_dump(mode="python") | {named_fees.removeprefix("zero-"): Decimal(0)}
        )
    if named_fees == "retained-mixed-zero":
        target = TransactionEvent.model_validate(
            target.model_dump(mode="python")
            | {"brokerage": Decimal(0), "gst": Decimal(0), "other_fees": Decimal(0)}
        )
    if named_fees in {"complete", "sparse", "zero-only", "aggregate-only"}:
        fee_shapes = {
            "complete": {
                "brokerage": Decimal("1"),
                "stamp_duty": Decimal("0"),
                "exchange_fee": Decimal("0"),
                "gst": Decimal("0"),
                "other_fees": Decimal("0"),
            },
            "sparse": {"brokerage": Decimal("1")},
            "zero-only": {"brokerage": Decimal("0")},
            "aggregate-only": {"trade_fee": Decimal("1")},
        }
        target = TransactionEvent.model_validate(
            target.model_dump(mode="python") | fee_shapes[named_fees]
        )
    if not (named_fees or "").startswith("retained-"):
        await _stage_native_raw_source(session, target)
    initial = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=cash_event("FUND", "BUY" if enriched_first_claim else "DEPOSIT", 8, "1000"),
        event_id=f"{portfolio_id}-fund",
        correlation_id="canonical-repair-proof",
    )
    assert initial.status is TransactionProcessingStatus.PROCESSED
    if not prior_claimed:
        # Native backdated processing sees this persisted source and materializes it,
        # without claiming its combined-processing semantic identity.
        session.add(canonical_transaction_record(target))
        await session.commit()
    backdated = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=cash_event("BACKDATED-FUND", "BUY" if enriched_first_claim else "DEPOSIT", 1, "50"),
        event_id=f"{portfolio_id}-backdated-fund",
        correlation_id="canonical-repair-proof",
    )
    assert backdated.status is TransactionProcessingStatus.PROCESSED
    if prior_claimed:
        processed = await persist_and_process_booked_transaction(
            session=session,
            context=context,
            event=target,
            event_id=f"{portfolio_id}-original-target",
            correlation_id="canonical-repair-proof",
        )
        assert processed.status is TransactionProcessingStatus.PROCESSED
        # Retained-state fixture representing the proved legacy history1/cashflow0 shape;
        # this setup is not a new reproduction of the original live delivery chronology.
        await session.execute(
            update(Cashflow)
            .where(
                Cashflow.transaction_id == target.transaction_id,
                Cashflow.epoch == 1,
            )
            .values(epoch=0)
        )
        await session.commit()
    identity = build_transaction_semantic_identity(
        map_transaction_event(
            target,
            event_id="identity-only",
            correlation_id="canonical-repair-proof",
        ).transaction
    )
    async with context.session_factory() as verification:
        claims = await verification.scalar(
            select(func.count(ProcessedEvent.id)).where(
                ProcessedEvent.service_name == "portfolio-transaction-processing",
                ProcessedEvent.semantic_key == identity.semantic_key,
                ProcessedEvent.tenant_id == TEST_TENANT_ID,
            )
        )
        history_epoch = await verification.scalar(
            select(PositionHistory.epoch).where(
                PositionHistory.transaction_id == target.transaction_id,
                PositionHistory.epoch == 1,
            )
        )
        original_flow = (
            await verification.execute(
                select(
                    Cashflow.id,
                    Cashflow.epoch,
                    Cashflow.amount,
                    Cashflow.cashflow_date,
                ).where(Cashflow.transaction_id == target.transaction_id)
            )
        ).one()
    assert claims == int(prior_claimed)
    assert history_epoch == 1
    assert original_flow.epoch == (0 if prior_claimed else 1)

    qcp_snapshot_epoch = None
    if (named_fees or "").startswith("retained-"):
        from src.services.query_control_plane_service.app.domain.analytics import (
            AnalyticsCashflowEpochEvidenceError,
        )
        from src.services.query_control_plane_service.app.infrastructure.analytics_timeseries_repository import (  # noqa: E501
            AnalyticsTimeseriesRepository,
        )

        # Serving-row fixture captures the independently persisted position epoch. No
        # valuation/calendar worker runs here; this is reader selection, not live QCP qualification.
        captured_epoch = await session.scalar(
            select(PositionState.epoch).where(
                PositionState.portfolio_id == portfolio_id, PositionState.security_id == security_id
            )
        )
        session.add(
            PositionTimeseries(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=target.transaction_date.date(),
                epoch=captured_epoch,
                bod_market_value=0,
                eod_market_value=0,
                bod_cashflow_position=0,
                eod_cashflow_position=0,
                bod_cashflow_portfolio=0,
                eod_cashflow_portfolio=0,
                quantity=target.quantity,
                cost=target.gross_transaction_amount,
            )
        )
        await session.commit()
        qcp = AnalyticsTimeseriesRepository(session)
        qcp_snapshot_epoch = await qcp.get_position_snapshot_epoch(
            portfolio_id=portfolio_id,
            start_date=target.transaction_date.date(),
            end_date=target.transaction_date.date(),
            security_ids=[security_id],
            position_ids=[],
            dimension_filters={},
            business_calendar_present=False,
        )
        assert qcp_snapshot_epoch == history_epoch == captured_epoch
        with pytest.raises(AnalyticsCashflowEpochEvidenceError):
            await qcp.list_position_cashflow_rows(
                portfolio_id=portfolio_id,
                security_ids=[security_id],
                valuation_dates=[target.transaction_date.date()],
                snapshot_epoch=qcp_snapshot_epoch,
            )

    if named_fees == "retained-concurrent":
        await _verify_concurrent_replay_authority(context, target, monkeypatch)

    class CapturingProducer:
        def __init__(self):
            self.messages = []

        def publish_message(self, **message):
            self.messages.append(message)

        def flush(self):
            return 0

    producer = CapturingProducer()
    if named_fees == "retained-no-raw":
        async with context.session_factory() as retention_check:
            canonical = (
                (
                    await retention_check.execute(
                        select(Transaction.__table__).where(
                            Transaction.transaction_id == target.transaction_id
                        )
                    )
                )
                .mappings()
                .one()
            )
            raw_count = await retention_check.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.event_type == "RawTransactionPersisted",
                    OutboxEvent.payload["transaction_id"].as_string() == target.transaction_id,
                )
            )
            print(
                {
                    "retained_prior_claims": claims,
                    "retained_raw_receipts": raw_count,
                    "stored_source_hash": canonical["payload_fingerprint"],
                    "current_economic_event_id": canonical["economic_event_id"],
                    "current_trade_fee": str(canonical["trade_fee"]),
                    "supported_expected_status": "processed",
                }
            )
            assert claims == 1 and raw_count == 0
    replay = build_replay_booked_transaction_use_case(
        session_factory=context.session_factory,
        kafka_producer=producer,
    )
    await replay.execute(
        ReplayBookedTransactionCommand(
            transaction_id=target.transaction_id,
            correlation_id="canonical-repair-proof",
        )
    )
    assert len(producer.messages) == 1
    published = producer.messages[0]
    replayed_event = TransactionEvent.model_validate(published["value"])
    assert replayed_event.epoch is None
    assert replayed_event.transaction_id == target.transaction_id
    assert replayed_event.transaction_date == target.transaction_date
    assert replayed_event.settlement_date == target.settlement_date
    for fee_name in ("brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"):
        assert getattr(replayed_event, fee_name) == getattr(target, fee_name)
    assert replayed_event.trade_fee == target.trade_fee
    tenant_id = await SqlAlchemyTransactionTenantAuthority(context.session_factory).resolve(
        portfolio_id=replayed_event.portfolio_id,
        asserted_tenant_id=replayed_event.tenant_id,
    )
    replayed_event = replayed_event.model_copy(update={"tenant_id": tenant_id})
    async with context.session_factory() as source_check:
        stored_source_hash = await source_check.scalar(
            select(Transaction.payload_fingerprint).where(
                Transaction.transaction_id == target.transaction_id
            )
        )
    replay_hash = build_transaction_payload_identity(
        replayed_event.model_dump(mode="python"), tenant_id=tenant_id
    ).payload_fingerprint
    if enriched_first_claim:
        assert claims == 0
        # Natural cost suffix enrichment does not imply booking-metadata defaults.
        assert target.net_cost is None
        assert replayed_event.net_cost == Decimal("1187")
        assert replayed_event.gross_cost == Decimal("1187")
        assert replayed_event.transaction_fx_rate_origin == "REFERENCE_DERIVED"
    print(
        {
            "prior_claimed": prior_claimed,
            "enriched_first_claim": enriched_first_claim,
            "named_fees": named_fees,
            "stored_original_source_hash": stored_source_hash,
            "current_canonical_replay_hash": replay_hash,
            "source_hash_matches_replay": stored_source_hash == replay_hash,
            "source_system": replayed_event.source_system,
            "economic_event_id": replayed_event.economic_event_id,
            "calculation_policy_id": replayed_event.calculation_policy_id,
            "current_net_cost": str(replayed_event.net_cost),
            "current_fx_origin": replayed_event.transaction_fx_rate_origin,
            "original_brokerage": str(target.brokerage),
            "replayed_brokerage": str(replayed_event.brokerage),
            "replayed_trade_fee": str(replayed_event.trade_fee),
        }
    )

    class DeliveredMessage:
        def topic(self):
            return published["topic"]

        def partition(self):
            return 0

        def offset(self):
            return 114101 if prior_claimed else 114102

        def headers(self):
            return published["headers"]

    delivered = DeliveredMessage()
    intent = _message_processing_intent(delivered)
    repair_delivery_id = _message_repair_delivery_id(delivered, processing_intent=intent)
    assert intent is TransactionProcessingIntent.REPAIR
    assert repair_delivery_id is None
    command = map_transaction_event(
        replayed_event,
        event_id=_message_event_id(delivered),
        correlation_id="canonical-repair-proof",
        processing_intent=intent,
        repair_delivery_id=repair_delivery_id,
    )
    if named_fees == "deferred":

        async def durable_repair_cut():
            async with context.session_factory() as verification:
                return [
                    list(
                        (
                            await verification.execute(
                                select(model.__table__).order_by(
                                    *model.__table__.primary_key.columns
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                    for model in (
                        Transaction,
                        TransactionCost,
                        ProcessedEvent,
                        OutboxEvent,
                        PositionHistory,
                        Cashflow,
                        PipelineStageState,
                        PositionState,
                    )
                ]

        before = await durable_repair_cut()
        staged = []

        def fail_deferred(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.lower().split())
            staged.append(normalized)
            if "select flush_deferred_portfolio_cashflow_source_cuts()" in normalized:
                raise RuntimeError("first-claimed repair deferred failure")

        engine = session.bind.sync_engine
        sqlalchemy_event.listen(engine, "before_cursor_execute", fail_deferred)
        try:
            with pytest.raises(RuntimeError, match="first-claimed repair deferred failure"):
                await context.use_case.execute(command)
        finally:
            sqlalchemy_event.remove(engine, "before_cursor_execute", fail_deferred)
        assert any("insert into position_history" in sql for sql in staged)
        assert any("insert into cashflows" in sql for sql in staged)
        assert await durable_repair_cut() == before
        print({"first_claimed_deferred_rollback": "full source and financial state cut unchanged"})
    admissions = []
    native_process = PositionHistoryProcessingAdapter.process

    async def observe_native_process(adapter, transaction, **kwargs):
        admissions.append(
            {
                "transaction_id": transaction.transaction_id,
                "rebuild_existing": kwargs["rebuild_existing"],
            }
        )
        return await native_process(adapter, transaction, **kwargs)

    with monkeypatch.context() as probe:
        probe.setattr(PositionHistoryProcessingAdapter, "process", observe_native_process)
        try:
            repaired = await context.use_case.execute(command)
        except TransactionProcessingRejected as exc:
            print(
                {
                    "prior_raw_claim": prior_claimed,
                    "canonical_epoch": replayed_event.epoch,
                    "physical_event_id": command.metadata.event_id,
                    "repair_delivery_id": repair_delivery_id,
                    "position_admissions": admissions,
                    "actual_rejection": exc.reason_code,
                    "retryable": exc.retryable,
                }
            )
            raise
    print(
        {
            "prior_raw_claim": prior_claimed,
            "canonical_epoch": replayed_event.epoch,
            "physical_event_id": command.metadata.event_id,
            "repair_delivery_id": repair_delivery_id,
            "position_admissions": admissions,
            "actual_status": repaired.status.value,
            "position_record_count": repaired.position_record_count,
            "cashflow_record_count": repaired.cashflow_record_count,
        }
    )
    assert repaired.status is TransactionProcessingStatus.PROCESSED
    assert repaired.position_record_count > 0
    assert repaired.cashflow_record_count > 0
    async with context.session_factory() as verification:
        flows = (
            await verification.scalars(
                select(Cashflow).where(
                    Cashflow.transaction_id == target.transaction_id,
                )
            )
        ).all()
        histories = (
            await verification.scalars(
                select(PositionHistory).where(
                    PositionHistory.transaction_id == target.transaction_id,
                )
            )
        ).all()
        selected_flow = max(flows, key=lambda row: (row.epoch, row.id))
        assert any(
            row.epoch == selected_flow.epoch and row.position_date == selected_flow.cashflow_date
            for row in histories
        )
        assert selected_flow.amount == -(Decimal("1187") + target.trade_fee)
        assert selected_flow.cashflow_date == target.transaction_date.date()
        if prior_claimed:
            retained = next(row for row in flows if row.id == original_flow.id)
            assert (retained.epoch, retained.amount, retained.cashflow_date) == (
                original_flow.epoch,
                original_flow.amount,
                original_flow.cashflow_date,
            )
        if qcp_snapshot_epoch is not None:
            qcp = AnalyticsTimeseriesRepository(verification)
            selected = await qcp.list_position_cashflow_rows(
                portfolio_id=portfolio_id,
                security_ids=[security_id],
                valuation_dates=[target.transaction_date.date()],
                snapshot_epoch=qcp_snapshot_epoch,
            )
            target_selected = [
                row for row in selected if row.transaction_id == target.transaction_id
            ]
            assert len(target_selected) == 1
            assert target_selected[0].epoch == qcp_snapshot_epoch == selected_flow.epoch
            assert target_selected[0].valuation_date == target.transaction_date.date()
            assert target_selected[0].amount == -(Decimal("1187") + target.trade_fee)
            assert original_flow.epoch != target_selected[0].epoch
            print(
                {
                    "actual_qcp_selected_snapshot_epoch": qcp_snapshot_epoch,
                    "selected_transaction": target_selected[0].transaction_id,
                    "original_orphan_cannot_satisfy_selected_reader": True,
                    "reader_serving_row_is_fixture_not_live_valuation": True,
                }
            )
    repeated = await context.use_case.execute(command)
    assert repeated.status is TransactionProcessingStatus.DUPLICATE


async def _verify_concurrent_replay_authority(context, target, monkeypatch):
    """Use real PostgreSQL blockers; committed source/receipt drift must not publish."""
    from portfolio_common.events import PortfolioEvent
    from portfolio_common.idempotency_repository import (
        IdempotencyRepository,
        SemanticEventClaimOutcome,
    )
    from portfolio_common.reprocessing_replay import ReprocessingReplayError

    from src.services.persistence_service.app.repositories.portfolio_repository import (
        PortfolioRepository,
    )

    async with (
        context.session_factory() as supported_writer,
        context.session_factory() as reader_witness,
    ):
        witness = await SqlAlchemyQualifiedTransactionReplayReader(
            reader_witness
        ).list_transactions_to_replay([target.transaction_id])
        assert len(witness) == 1
        retained = (
            await supported_writer.execute(
                select(ProcessedEvent.semantic_key, ProcessedEvent.payload_fingerprint).where(
                    ProcessedEvent.tenant_id == TEST_TENANT_ID,
                    ProcessedEvent.service_name == "portfolio-transaction-processing",
                    ProcessedEvent.semantic_key
                    == build_transaction_semantic_identity(
                        map_transaction_event(
                            target.model_copy(update={"tenant_id": TEST_TENANT_ID}),
                            event_id="identity",
                        ).transaction
                    ).semantic_key,
                )
            )
        ).one()
        repository = IdempotencyRepository(supported_writer)
        for digest, expected in (
            (retained.payload_fingerprint, SemanticEventClaimOutcome.SEMANTIC_DUPLICATE),
            ("sha256:" + "f" * 64, SemanticEventClaimOutcome.SEMANTIC_CONFLICT),
        ):
            assert (
                await asyncio.wait_for(
                    repository.claim_semantic_event_processing(
                        event_id="supported-receipt-concurrent",
                        portfolio_id=target.portfolio_id,
                        service_name="portfolio-transaction-processing",
                        semantic_key=retained.semantic_key,
                        payload_fingerprint=digest,
                        tenant_id=TEST_TENANT_ID,
                    ),
                    timeout=5,
                )
                is expected
            )
        await supported_writer.commit()
        await reader_witness.rollback()
        print({"supported_receipt_writer": "duplicate/conflict preserve committed original fence"})

    for reference in ("receipt", "source", "supported-root"):
        async with context.session_factory() as writer, context.session_factory() as reader:
            if reference == "receipt":
                receipt = (
                    await writer.execute(
                        select(ProcessedEvent.id, ProcessedEvent.payload_fingerprint).where(
                            ProcessedEvent.tenant_id == TEST_TENANT_ID,
                            ProcessedEvent.service_name == "portfolio-transaction-processing",
                            ProcessedEvent.semantic_key.like(
                                f"transaction-processing:v1:{target.portfolio_id}:{target.transaction_id}:%"
                            ),
                        )
                    )
                ).one()
                await writer.execute(
                    update(ProcessedEvent)
                    .where(ProcessedEvent.id == receipt.id)
                    .values(payload_fingerprint="sha256:" + "f" * 64)
                )
            elif reference == "source":
                await writer.execute(
                    select(Portfolio.portfolio_id)
                    .where(Portfolio.portfolio_id == target.portfolio_id)
                    .with_for_update()
                )
                await writer.execute(
                    update(Transaction)
                    .where(Transaction.transaction_id == target.transaction_id)
                    .values(quantity=target.quantity + 1)
                )
            else:
                root = (
                    (
                        await writer.execute(
                            select(Portfolio.__table__).where(
                                Portfolio.portfolio_id == target.portfolio_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                root_event = PortfolioEvent.model_validate(
                    {name: root[name] for name in PortfolioEvent.model_fields if name in root}
                )
                await PortfolioRepository(writer).create_or_update_portfolio(
                    root_event.model_copy(update={"objective": "supported-lock-proof"})
                )
            reader_pid = await reader.scalar(text("select pg_backend_pid()"))
            waiting = asyncio.Event()
            native_execute = reader.execute

            async def observe_lock(statement, *args, **kwargs):
                sql = str(statement)
                awaited_reference = "processed_events" if reference == "receipt" else "portfolios"
                if awaited_reference in sql and ("FOR UPDATE" in sql or "FOR SHARE" in sql):
                    waiting.set()
                return await native_execute(statement, *args, **kwargs)

            with monkeypatch.context() as probe:
                probe.setattr(reader, "execute", observe_lock)
                task = asyncio.create_task(
                    SqlAlchemyQualifiedTransactionReplayReader(reader).list_transactions_to_replay(
                        [target.transaction_id]
                    )
                )
                try:
                    await asyncio.wait_for(waiting.wait(), timeout=5)
                    async with context.session_factory() as inspector:
                        for _ in range(40):
                            blocked = await inspector.scalar(
                                text("select cardinality(pg_blocking_pids(:pid))"),
                                {"pid": reader_pid},
                            )
                            if blocked:
                                break
                            await asyncio.sleep(0.05)
                    assert blocked > 0, (
                        "Native source reader must actually wait on retained authority"
                    )
                    await writer.commit()
                    if reference == "supported-root":
                        rows = await asyncio.wait_for(task, timeout=5)
                        assert len(rows) == 1 and rows[0].transaction_id == target.transaction_id
                    else:
                        with pytest.raises(ReprocessingReplayError):
                            await asyncio.wait_for(task, timeout=5)
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                    await reader.rollback()
                    await writer.rollback()
            async with context.session_factory() as restore:
                if reference == "receipt":
                    await restore.execute(
                        update(ProcessedEvent)
                        .where(ProcessedEvent.id == receipt.id)
                        .values(payload_fingerprint=receipt.payload_fingerprint)
                    )
                elif reference == "source":
                    await restore.execute(
                        update(Transaction)
                        .where(Transaction.transaction_id == target.transaction_id)
                        .values(quantity=target.quantity)
                    )
                else:
                    await PortfolioRepository(restore).create_or_update_portfolio(root_event)
                await restore.commit()
            print(
                {
                    "concurrent_reference": reference,
                    "actual_pg_blocker_count": blocked,
                    "committed_drift_refused_before_publication": reference != "supported-root",
                    "supported_root_writer_preserves_tenant_and_receipt": reference
                    == "supported-root",
                }
            )
    async with context.session_factory() as fenced:
        before = (
            (
                await fenced.execute(
                    select(PositionState.__table__).where(
                        PositionState.portfolio_id == target.portfolio_id,
                        PositionState.security_id == target.security_id,
                    )
                )
            )
            .mappings()
            .one()
        )
        store = SqlAlchemyPositionRecalculationStateStore(PositionStateRepository(fenced))
        assert before["epoch"] > 0
        assert (
            await store.advance_epoch(
                portfolio_id=target.portfolio_id,
                security_id=target.security_id,
                expected_epoch=before["epoch"] - 1,
                watermark_date=target.transaction_date.date(),
            )
            is None
        )
        assert not await store.rearm_generation(
            portfolio_id=target.portfolio_id,
            security_id=target.security_id,
            expected_epoch=before["epoch"] - 1,
            watermark_date=target.transaction_date.date(),
        )
        after = (
            (
                await fenced.execute(
                    select(PositionState.__table__).where(
                        PositionState.portfolio_id == target.portfolio_id,
                        PositionState.security_id == target.security_id,
                    )
                )
            )
            .mappings()
            .one()
        )
        assert dict(after) == dict(before)
        await fenced.rollback()
        print({"native_stale_CAS_and_rearm": "both refused; exact state unchanged"})


_ALTERED_REPAIR_SOURCE_FIELDS = (
    "gross",
    "quantity",
    "date",
    "source_fx_value",
    "source_fx_absence",
    "source_system",
    "economic_event_id",
    "tenant",
)


async def _stage_native_raw_source(session, source):
    """Stage the native persistence completion payload without a Kafka connection."""
    consumer = object.__new__(TransactionPersistenceConsumer)
    completion = consumer.get_outbox_event(source)
    await OutboxRepository(session).create_outbox_event(
        **completion,
        correlation_id="original-source-authority-proof",
    )
    await session.commit()


async def _observe_cost_receipt_source_authority(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
    altered_field: str,
    *,
    retained_row_conflict: bool = False,
    disable_guard: bool = False,
) -> bool:
    """Require actual pre-cost refusal and complete native rollback for altered authority."""
    portfolio_id = f"RECEIPT-AUTHORITY-{altered_field}"
    security_id = f"RECEIPT-CASH-{altered_field}"
    session = async_db_session
    session.add_all(
        [
            portfolio_record(portfolio_id, base_currency="SGD"),
            instrument_record(
                security_id,
                name="Receipt authority cash",
                isin=portfolio_id,
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            FxRate(
                from_currency="USD",
                to_currency="SGD",
                rate_date=date(2026, 3, 1),
                rate=Decimal("1.40"),
            ),
        ]
    )
    await session.commit()
    context = transaction_processing_test_context(session)
    original = booked_transaction_event(
        transaction_id=f"{portfolio_id}-SOURCE",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 11, 10, tzinfo=UTC),
        settlement_date=datetime(2026, 3, 11, 16, tzinfo=UTC),
        transaction_type="BUY",
        quantity="1187",
        price="1",
        gross_amount="1187",
        transaction_fx_rate=Decimal("1.30"),
        source_system="CANONICAL",
        economic_event_id=f"{portfolio_id}-ECONOMIC",
    )
    initial = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=original.model_copy(
            update={
                "transaction_id": f"{portfolio_id}-INITIAL",
                "transaction_type": "DEPOSIT",
                "transaction_date": datetime(2026, 3, 15, 10, tzinfo=UTC),
            }
        ),
        event_id=f"{portfolio_id}-initial",
        correlation_id="receipt-authority-proof",
    )
    assert initial.status is TransactionProcessingStatus.PROCESSED
    session.add(canonical_transaction_record(original))
    await _stage_native_raw_source(session, original)
    await session.commit()
    backdated = await persist_and_process_booked_transaction(
        session=session,
        context=context,
        event=original.model_copy(
            update={
                "transaction_id": f"{portfolio_id}-BACKDATED",
                "transaction_type": "DEPOSIT",
                "transaction_date": datetime(2026, 3, 1, 10, tzinfo=UTC),
            }
        ),
        event_id=f"{portfolio_id}-backdated",
        correlation_id="receipt-authority-proof",
    )
    assert backdated.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as claim_check:
        assert (
            await claim_check.scalar(
                select(func.count(ProcessedEvent.id)).where(
                    ProcessedEvent.service_name == "portfolio-transaction-processing",
                    ProcessedEvent.semantic_key.like(f"%:{original.transaction_id}:%"),
                )
            )
            == 0
        )

    async def durable_cut():
        async with context.session_factory() as verification:
            source = dict(
                (
                    await verification.execute(
                        select(Transaction.__table__).where(
                            Transaction.transaction_id == original.transaction_id,
                        )
                    )
                )
                .mappings()
                .one()
            )
            claims = (
                await verification.execute(
                    select(
                        ProcessedEvent.id,
                        ProcessedEvent.event_id,
                        ProcessedEvent.semantic_key,
                        ProcessedEvent.payload_fingerprint,
                        ProcessedEvent.tenant_id,
                    )
                    .where(ProcessedEvent.portfolio_id == portfolio_id)
                    .order_by(ProcessedEvent.id)
                )
            ).all()
            events = (
                await verification.execute(
                    select(OutboxEvent.id, OutboxEvent.payload)
                    .where(
                        OutboxEvent.aggregate_id == portfolio_id,
                    )
                    .order_by(OutboxEvent.id)
                )
            ).all()
            flows = (
                await verification.execute(
                    select(Cashflow.id, Cashflow.epoch, Cashflow.amount)
                    .where(
                        Cashflow.portfolio_id == portfolio_id,
                    )
                    .order_by(Cashflow.id)
                )
            ).all()
            history = (
                await verification.execute(
                    select(
                        PositionHistory.id,
                        PositionHistory.epoch,
                        PositionHistory.quantity,
                    )
                    .where(PositionHistory.portfolio_id == portfolio_id)
                    .order_by(PositionHistory.id)
                )
            ).all()
            costs = (
                await verification.execute(
                    select(TransactionCost.__table__)
                    .where(TransactionCost.transaction_id == original.transaction_id)
                    .order_by(TransactionCost.id)
                )
            ).all()
            readiness = (
                await verification.execute(
                    select(PipelineStageState.__table__)
                    .where(PipelineStageState.portfolio_id == portfolio_id)
                    .order_by(PipelineStageState.id)
                )
            ).all()
            return source, claims, events, flows, history, costs, readiness

    before = await durable_cut()
    original_identity = build_transaction_payload_identity(
        original.model_dump(mode="python"),
        tenant_id=TEST_TENANT_ID,
    )
    assert before[0]["payload_fingerprint"] == original_identity.payload_fingerprint
    mutations = {
        "gross": {"gross_transaction_amount": Decimal("1200")},
        "quantity": {"quantity": Decimal("1200")},
        "date": {"transaction_date": datetime(2026, 3, 12, 10, tzinfo=UTC)},
        "source_fx_value": {"transaction_fx_rate": Decimal("1.50")},
        "source_fx_absence": {"transaction_fx_rate": None, "transaction_fx_rate_origin": None},
        "source_system": {"source_system": "ALTERED"},
        "economic_event_id": {"economic_event_id": f"{portfolio_id}-ALTERED"},
        "tenant": {"tenant_id": "OTHER-TENANT"},
    }
    altered = original.model_copy(update=mutations[altered_field])
    if retained_row_conflict:
        # Reproduce the already-observed cost writer's overwrite with the original hash retained.
        # This isolated retained-row fixture does not claim a live corruption chronology.
        await session.execute(
            update(Transaction)
            .where(Transaction.transaction_id == original.transaction_id)
            .values(transaction_fx_rate=altered.transaction_fx_rate)
        )
        await session.commit()
        before = await durable_cut()
        assert before[0]["payload_fingerprint"] == original_identity.payload_fingerprint
    authority = SqlAlchemyTransactionTenantAuthority(context.session_factory)
    if altered_field == "tenant":
        with pytest.raises(TransactionTenantAuthorityMismatch):
            await authority.resolve(portfolio_id=portfolio_id, asserted_tenant_id=altered.tenant_id)
        tenant_id = altered.tenant_id
    else:
        tenant_id = await authority.resolve(
            portfolio_id=portfolio_id,
            asserted_tenant_id=altered.tenant_id,
        )
    altered = altered.model_copy(update={"tenant_id": tenant_id})
    altered_identity = build_transaction_payload_identity(
        altered.model_dump(mode="python"),
        tenant_id=tenant_id,
    )
    if altered_field == "tenant":
        # Tenant belongs to the semantic key/DB ownership boundary, not payload hashing.
        assert altered_identity.semantic_key != original_identity.semantic_key
    else:
        assert altered_identity.payload_fingerprint != before[0]["payload_fingerprint"]
    command = map_transaction_event(
        altered,
        event_id=f"{portfolio_id}-altered-repair",
        correlation_id="receipt-authority-proof",
        processing_intent=TransactionProcessingIntent.REPAIR,
        repair_delivery_id=f"{portfolio_id}-altered-repair-intent",
    )
    observed = []

    async def refuse_cost_if_guard_is_disabled(adapter, transaction, **kwargs):
        observed.append(transaction.transaction_id)
        raise AssertionError("Altered source reached cost writes: pre-cost guard is missing")

    with monkeypatch.context() as probe:
        probe.setattr(CostBasisProcessingAdapter, "process", refuse_cost_if_guard_is_disabled)
        if disable_guard:

            async def disabled_validation(adapter, transaction):
                return None

            probe.setattr(
                CostBasisProcessingAdapter,
                "validate_unversioned_repair_source",
                disabled_validation,
            )
            with pytest.raises(AssertionError, match="pre-cost guard is missing"):
                await context.use_case.execute(command)
            assert observed == [original.transaction_id]
            assert await durable_cut() == before
            print(
                {"disabled_guard_discrimination": "altered source reached cost; rollback unchanged"}
            )
            return True
        with pytest.raises(TransactionProcessingRejected) as rejected:
            await context.use_case.execute(command)
    assert rejected.value.reason_code in {
        "repair_source_authority_mismatch",
        "repair_source_owner_mismatch",
        "repair_original_source_unavailable",
    }
    assert rejected.value.retryable is False
    assert observed == []
    after = await durable_cut()
    assert after == before, "Native UOW must roll back cost/source/claim/event writes"
    print(
        {
            "field": altered_field,
            "production_refusal": rejected.value.reason_code,
            "cost_not_executed": True,
            "durable_source_claims_events_flows_history_costs_readiness_unchanged": True,
        }
    )
    return False


@pytest.mark.lifecycle
@pytest.mark.parametrize("altered_field", _ALTERED_REPAIR_SOURCE_FIELDS)
async def test_repair_source_authority_refuses_before_cost_writes(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
    altered_field: str,
) -> None:
    await _observe_cost_receipt_source_authority(
        clean_db,
        async_db_session,
        monkeypatch,
        altered_field,
    )


@pytest.mark.lifecycle
async def test_repair_refuses_current_row_echo_conflicting_with_original_source_hash(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
):
    await _observe_cost_receipt_source_authority(
        clean_db,
        async_db_session,
        monkeypatch,
        "source_fx_value",
        retained_row_conflict=True,
    )


@pytest.mark.lifecycle
async def test_disabled_repair_guard_exposes_altered_source_before_cost_boundary(
    clean_db, async_db_session, monkeypatch
):
    assert await _observe_cost_receipt_source_authority(
        clean_db, async_db_session, monkeypatch, "gross", disable_guard=True
    )
