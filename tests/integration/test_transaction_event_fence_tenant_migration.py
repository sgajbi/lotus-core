"""PostgreSQL proof for tenant-scoped transaction event fences."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c167b2c3d52e_fix_scope_transaction_event_fences.py"
)

PORTFOLIO_INSERT = text(
    """
    INSERT INTO portfolios (
        portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
        risk_exposure, investment_time_horizon, portfolio_type,
        booking_center_code, client_id, is_leverage_allowed, status
    ) VALUES (
        :portfolio_id, :tenant_id, :legal_book_id, 'USD', DATE '2026-01-01',
        'balanced', 'long_term', 'discretionary', 'SG_BOOKING',
        :client_id, FALSE, 'active'
    )
    """
)

LEGACY_FENCE_INSERT = text(
    """
    INSERT INTO processed_events (
        event_id, portfolio_id, service_name, correlation_id,
        semantic_key, payload_fingerprint
    ) VALUES (
        :event_id, :portfolio_id, :service_name, :correlation_id,
        :semantic_key, :payload_fingerprint
    )
    """
)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def test_transaction_fence_cutover_fails_closed_and_scopes_collisions_by_tenant(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        if "tenant_id" in {
            column["name"] for column in inspect(connection).get_columns("processed_events")
        }:
            migration["downgrade"]()

        for tenant, portfolio, client in (
            ("tenant-a", "PORT-FENCE-A", "CLIENT-A"),
            ("tenant-b", "PORT-FENCE-B", "CLIENT-B"),
        ):
            connection.execute(
                PORTFOLIO_INSERT,
                {
                    "portfolio_id": portfolio,
                    "tenant_id": tenant,
                    "legal_book_id": f"BOOK-{tenant}",
                    "client_id": client,
                },
            )

        connection.execute(
            LEGACY_FENCE_INSERT,
            {
                "event_id": "SOURCE-TXN-SHARED",
                "portfolio_id": "PORT-MISSING",
                "service_name": "portfolio-transaction-processing",
                "correlation_id": "corr-unattributable",
                "semantic_key": "semantic-shared",
                "payload_fingerprint": "fingerprint-a",
            },
        )
        failed_cutover = connection.begin_nested()
        with pytest.raises(DBAPIError, match="unattributable"):
            migration["upgrade"]()
        failed_cutover.rollback()
        connection.execute(text("DELETE FROM processed_events WHERE portfolio_id = 'PORT-MISSING'"))

        connection.execute(
            LEGACY_FENCE_INSERT,
            {
                "event_id": "SOURCE-TXN-SHARED",
                "portfolio_id": "PORT-FENCE-A",
                "service_name": "portfolio-transaction-processing",
                "correlation_id": "corr-a",
                "semantic_key": "semantic-shared",
                "payload_fingerprint": "fingerprint-a",
            },
        )
        migration["upgrade"]()

        assert (
            connection.scalar(
                text("SELECT tenant_id FROM processed_events WHERE portfolio_id = 'PORT-FENCE-A'")
            )
            == "tenant-a"
        )

        connection.execute(
            text(
                """
                INSERT INTO processed_events (
                    event_id, portfolio_id, service_name, tenant_id,
                    correlation_id, semantic_key, payload_fingerprint
                ) VALUES (
                    'SOURCE-TXN-SHARED', 'PORT-FENCE-B',
                    'portfolio-transaction-processing', 'tenant-b',
                    'corr-b', 'semantic-shared', 'fingerprint-b'
                )
                """
            )
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM processed_events WHERE event_id = 'SOURCE-TXN-SHARED'")
            )
            == 2
        )

        same_tenant_duplicate = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO processed_events (
                        event_id, portfolio_id, service_name, tenant_id,
                        correlation_id, semantic_key, payload_fingerprint
                    ) VALUES (
                        'SOURCE-TXN-SHARED', 'PORT-FENCE-A',
                        'portfolio-transaction-processing', 'tenant-a',
                        'corr-duplicate', 'semantic-other', 'fingerprint-other'
                    )
                    """
                )
            )
        same_tenant_duplicate.rollback()

        missing_tenant = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                LEGACY_FENCE_INSERT,
                {
                    "event_id": "SOURCE-TXN-NO-TENANT",
                    "portfolio_id": "PORT-FENCE-A",
                    "service_name": "portfolio-transaction-processing",
                    "correlation_id": "corr-no-tenant",
                    "semantic_key": "semantic-no-tenant",
                    "payload_fingerprint": "fingerprint-no-tenant",
                },
            )
        missing_tenant.rollback()

        unsafe_downgrade = connection.begin_nested()
        with pytest.raises(DBAPIError, match="cross-tenant key collision"):
            migration["downgrade"]()
        unsafe_downgrade.rollback()

        index_names = {
            index["name"] for index in inspect(connection).get_indexes("processed_events")
        }
        assert {
            "uq_processed_events_tenant_event_service",
            "uq_processed_events_global_event_service",
            "uq_processed_events_tenant_service_semantic_key",
            "uq_processed_events_global_service_semantic_key",
        }.issubset(index_names)
