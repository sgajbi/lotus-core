"""Populated PostgreSQL upgrade proof for corporate-action source authority."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]

MIGRATION_DIRECTORY = Path(__file__).resolve().parents[2] / "alembic" / "versions"
MIGRATION_PATHS = (
    MIGRATION_DIRECTORY / "c152b2c3d519_feat_add_corporate_action_event_graph.py",
    MIGRATION_DIRECTORY / "c153b2c3d520_feat_add_corporate_action_execution_releases.py",
    MIGRATION_DIRECTORY / "c154b2c3d521_perf_index_corporate_action_support.py",
    MIGRATION_DIRECTORY / "c155b2c3d522_fix_forward_corporate_action_authority.py",
)


def test_populated_c152_upgrade_preserves_manifest_and_backfills_transaction_authority(
    db_engine,
    clean_db,
) -> None:
    migrations = [runpy.run_path(str(path)) for path in MIGRATION_PATHS]
    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        for migration in migrations:
            migration["upgrade"].__globals__["op"] = operations
            migration["downgrade"].__globals__["op"] = operations
        _normalize_before_c152(connection, migrations)
        migrations[0]["upgrade"]()
        _seed_portfolio_and_transactions(connection)

        legacy = _manifest("LEGACY")
        legacy_payload = _manifest_payload(legacy, book_scoped=False)
        legacy_hash_before_upgrade = connection.scalar(
            text("SELECT canonical_ca_manifest_payload_hash(CAST(:payload AS jsonb))"),
            {"payload": json.dumps(legacy_payload)},
        )
        legacy_event_id = _insert_event(connection, legacy)
        _insert_manifest(
            connection,
            legacy_event_id,
            legacy,
            legacy_payload,
            manifest_hash=legacy_hash_before_upgrade,
        )
        source_child = legacy.expected_children[0]
        connection.execute(
            text(
                """
                INSERT INTO corporate_action_child_observations (
                    event_id, observation_sequence, transaction_id, transaction_epoch,
                    delivery_event_id, correlation_id, observed_content_hash,
                    observed_payload, observed_at
                ) VALUES (
                    :event_id, 1, :transaction_id, 1, 'legacy-delivery-1',
                    'legacy-correlation', :content_hash, CAST(:payload AS jsonb),
                    TIMESTAMPTZ '2026-08-09 01:01:00+00'
                )
                """
            ),
            {
                "event_id": legacy_event_id,
                "transaction_id": source_child.transaction_id,
                "content_hash": source_child.content_hash,
                "payload": json.dumps(source_child.lineage_payload()),
            },
        )
        expected_fingerprint = f"sha256:{'a' * 64}"
        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, tenant_id,
                    semantic_key, payload_fingerprint
                ) VALUES (
                    'legacy-processed-1', :portfolio_id,
                    'portfolio-transaction-processing', :tenant_id,
                    :semantic_key, :fingerprint
                )
                """
            ),
            {
                "portfolio_id": legacy.portfolio_id,
                "tenant_id": legacy.tenant_id,
                "semantic_key": (
                    "transaction-processing:v1:"
                    f"{legacy.portfolio_id}:{source_child.transaction_id}:1"
                ),
                "fingerprint": expected_fingerprint,
            },
        )

        for migration in migrations[1:]:
            migration["upgrade"]()

        assert (
            connection.scalar(
                text(
                    "SELECT transaction_payload_fingerprint "
                    "FROM corporate_action_child_observations "
                    "WHERE delivery_event_id = 'legacy-delivery-1'"
                )
            )
            == expected_fingerprint
        )
        observation_column = next(
            column
            for column in inspect(connection).get_columns("corporate_action_child_observations")
            if column["name"] == "transaction_payload_fingerprint"
        )
        assert observation_column["nullable"] is False
        assert (
            connection.scalar(
                text("SELECT canonical_ca_manifest_payload_hash(CAST(:payload AS jsonb))"),
                {"payload": json.dumps(legacy_payload)},
            )
            == legacy_hash_before_upgrade
        )

        scoped = _manifest("SCOPED")
        scoped_payload = _manifest_payload(scoped, book_scoped=True)
        scoped_hash = connection.scalar(
            text("SELECT canonical_ca_manifest_payload_hash(CAST(:payload AS jsonb))"),
            {"payload": json.dumps(scoped_payload)},
        )
        assert scoped_hash == scoped.content_hash
        scoped_event_id = _insert_event(connection, scoped)
        _insert_manifest(
            connection,
            scoped_event_id,
            scoped,
            scoped_payload,
            manifest_hash=scoped_hash,
        )
        tampered_payload = dict(scoped_payload)
        tampered_payload["legal_book_id"] = "PB-OTHER"
        tampered_hash = connection.scalar(
            text("SELECT canonical_ca_manifest_payload_hash(CAST(:payload AS jsonb))"),
            {"payload": json.dumps(tampered_payload)},
        )
        with pytest.raises(IntegrityError, match="book scope conflicts with parent event"):
            savepoint = connection.begin_nested()
            try:
                _insert_manifest(
                    connection,
                    _insert_event(connection, _manifest("TAMPERED")),
                    _manifest("TAMPERED"),
                    tampered_payload,
                    manifest_hash=tampered_hash,
                )
            finally:
                savepoint.rollback()


def test_c153_upgrade_fails_closed_without_transaction_semantic_authority(
    db_engine,
    clean_db,
) -> None:
    migrations = [runpy.run_path(str(path)) for path in MIGRATION_PATHS]
    connection = db_engine.connect()
    transaction = connection.begin()
    try:
        operations = Operations(MigrationContext.configure(connection))
        for migration in migrations:
            migration["upgrade"].__globals__["op"] = operations
            migration["downgrade"].__globals__["op"] = operations
        _normalize_before_c152(connection, migrations)
        migrations[0]["upgrade"]()
        _seed_portfolio_and_transactions(connection)
        manifest = _manifest("LEGACY")
        event_id = _insert_event(connection, manifest)
        source_child = manifest.expected_children[0]
        connection.execute(
            text(
                """
                INSERT INTO corporate_action_child_observations (
                    event_id, observation_sequence, transaction_id, transaction_epoch,
                    delivery_event_id, correlation_id, observed_content_hash,
                    observed_payload, observed_at
                ) VALUES (
                    :event_id, 1, :transaction_id, 1, 'legacy-without-authority',
                    'legacy-correlation', :content_hash, CAST(:payload AS jsonb),
                    TIMESTAMPTZ '2026-08-09 01:01:00+00'
                )
                """
            ),
            {
                "event_id": event_id,
                "transaction_id": source_child.transaction_id,
                "content_hash": source_child.content_hash,
                "payload": json.dumps(source_child.lineage_payload()),
            },
        )

        savepoint = connection.begin_nested()
        with pytest.raises(
            IntegrityError,
            match="lacks deterministic transaction semantic authority",
        ):
            migrations[1]["upgrade"]()
        savepoint.rollback()
        assert (
            connection.scalar(
                text(
                    """
                SELECT trigger.tgenabled
                FROM pg_trigger AS trigger
                WHERE trigger.tgname = 'trg_ca_child_observation_immutable'
                """
                )
            )
            == "O"
        )
    finally:
        transaction.rollback()
        connection.close()


def _normalize_before_c152(connection, migrations: list[dict[str, Any]]) -> None:
    has_book_scope_function = (
        connection.scalar(
            text("SELECT to_regprocedure('enforce_ca_manifest_payload_book_scope()')")
        )
        is not None
    )
    if has_book_scope_function:
        has_book_scope_trigger = bool(
            connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                    "WHERE tgname = 'trg_ca_manifest_payload_book_scope')"
                )
            )
        )
        if has_book_scope_trigger:
            migrations[3]["downgrade"]()
        else:
            connection.execute(
                text("DROP FUNCTION IF EXISTS enforce_ca_manifest_payload_book_scope()")
            )
    inspector = inspect(connection)
    if "corporate_action_events" in inspector.get_table_names() and any(
        index["name"] == "ix_ca_event_book_scope_updated"
        for index in inspector.get_indexes("corporate_action_events")
    ):
        migrations[2]["downgrade"]()
    if "corporate_action_execution_releases" in inspect(connection).get_table_names():
        migrations[1]["downgrade"]()
    if "corporate_action_events" in inspect(connection).get_table_names():
        migrations[0]["downgrade"]()


def _manifest(suffix: str) -> corporate_action.CorporateActionParentManifest:
    source = corporate_action.CorporateActionEventChild(
        transaction_id=f"CA-SOURCE-{suffix}",
        transaction_type="DEMERGER_OUT",
        child_role="SOURCE_POSITION_REDUCE",
        instrument_id="SOURCE-SEC",
        source_instrument_id="SOURCE-SEC",
    )
    target = corporate_action.CorporateActionEventChild(
        transaction_id=f"CA-TARGET-{suffix}",
        transaction_type="DEMERGER_IN",
        child_role="TARGET_POSITION_ADD",
        dependency_transaction_ids=(source.transaction_id,),
        instrument_id="TARGET-SEC",
        source_instrument_id="SOURCE-SEC",
        target_instrument_id="TARGET-SEC",
    )
    return corporate_action.CorporateActionParentManifest(
        corporate_action_event_id=f"CA-EVENT-{suffix}",
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="CA-PORT-UPGRADE",
        linked_transaction_group_id=f"CA-GROUP-{suffix}",
        parent_event_reference=f"CA-PARENT-{suffix}",
        corporate_action_type="DEMERGER",
        version=1,
        completion_declared=True,
        expected_children=(source, target),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id=f"SOURCE-{suffix}",
            source_revision="1",
            source_content_hash="b" * 64,
            observed_at=datetime(2026, 8, 9, 1, tzinfo=UTC),
        ),
    )


def _manifest_payload(
    manifest: corporate_action.CorporateActionParentManifest,
    *,
    book_scoped: bool,
) -> dict[str, object]:
    payload = cast(dict[str, object], manifest.lineage_payload())
    source_payload = dict(cast(dict[str, object], payload["source_reference"]))
    source_payload["observed_at"] = manifest.source_reference.observed_at.isoformat()
    payload["source_reference"] = source_payload
    if not book_scoped:
        payload.pop("tenant_id")
        payload.pop("legal_book_id")
    return payload


def _insert_event(connection, manifest: corporate_action.CorporateActionParentManifest) -> int:
    event_id = connection.scalar(
        text(
            """
            INSERT INTO corporate_action_events (
                tenant_id, legal_book_id, portfolio_id, corporate_action_event_id,
                linked_transaction_group_id, parent_event_reference
            ) VALUES (
                :tenant_id, :legal_book_id, :portfolio_id, :event_id, :group_id, :parent_id
            ) RETURNING id
            """
        ),
        {
            "tenant_id": manifest.tenant_id,
            "legal_book_id": manifest.legal_book_id,
            "portfolio_id": manifest.portfolio_id,
            "event_id": manifest.corporate_action_event_id,
            "group_id": manifest.linked_transaction_group_id,
            "parent_id": manifest.parent_event_reference,
        },
    )
    assert isinstance(event_id, int)
    return event_id


def _insert_manifest(
    connection,
    event_id: int,
    manifest,
    payload: dict[str, object],
    *,
    manifest_hash: str,
) -> int:
    manifest_id = connection.scalar(
        text(
            """
            INSERT INTO corporate_action_manifest_versions (
                event_id, manifest_version, corporate_action_type, completion_declared,
                source_system, source_record_id, source_revision, source_content_hash,
                source_observed_at, manifest_content_hash, expected_node_count,
                expected_edge_count, opened_observation_sequence, manifest_payload
            ) VALUES (
                :event_id, 1, 'DEMERGER', true, 'custodian-ca', :source_record_id,
                '1', :source_content_hash, TIMESTAMPTZ '2026-08-09 01:00:00+00',
                :manifest_hash, 2, 1, 0, CAST(:payload AS jsonb)
            ) RETURNING id
            """
        ),
        {
            "event_id": event_id,
            "source_record_id": manifest.source_reference.source_record_id,
            "source_content_hash": manifest.source_reference.source_content_hash,
            "manifest_hash": manifest_hash,
            "payload": json.dumps(payload),
        },
    )
    assert isinstance(manifest_id, int)
    return manifest_id


def _seed_portfolio_and_transactions(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                'CA-PORT-UPGRADE', 'TENANT-SG', 'PB-SG-01', 'USD', DATE '2026-01-01',
                'BALANCED', 'LONG_TERM', 'DISCRETIONARY', 'SG', 'CLIENT-UPGRADE',
                false, 'ACTIVE'
            );
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date, trade_fee
            ) VALUES
            ('CA-SOURCE-LEGACY', 'CA-PORT-UPGRADE', 'SOURCE-SEC', 'SOURCE-SEC',
             'DEMERGER_OUT', 10, 100, 1000, 'USD', 'USD',
             TIMESTAMPTZ '2026-08-09 01:00:00+00', 0),
            ('CA-TARGET-LEGACY', 'CA-PORT-UPGRADE', 'TARGET-SEC', 'TARGET-SEC',
             'DEMERGER_IN', 10, 100, 1000, 'USD', 'USD',
             TIMESTAMPTZ '2026-08-09 01:00:00+00', 0);
            """
        )
    )
