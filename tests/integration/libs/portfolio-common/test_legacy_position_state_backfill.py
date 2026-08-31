"""PostgreSQL proof that legacy position evidence remains visible after epoch fencing."""

from __future__ import annotations

import runpy
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from src.services.calculators.position_valuation_calculator.app.repositories import (
    valuation_repository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c159b2c3d526_fix_backfill_legacy_position_state.py"
)


def _run_upgrade(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["upgrade"]()


async def _apply_backfill(migration: dict[str, Any], connection: AsyncConnection) -> None:
    await connection.run_sync(lambda sync_connection: _run_upgrade(migration, sync_connection))


async def test_backfill_restores_missing_snapshot_and_history_state_without_overwriting_live_state(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))
    await async_db_session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, base_currency, open_date, risk_exposure,
                investment_time_horizon, portfolio_type, booking_center_code,
                client_id, status, is_leverage_allowed
            ) VALUES
                ('LEGACY-SNAPSHOT', 'LEGACY-STATE-TENANT', 'USD', DATE '2024-01-01',
                 'balanced', 'medium',
                 'discretionary', 'SGPB', 'LEGACY-CLIENT-1', 'ACTIVE', false),
                ('LEGACY-HISTORY', 'LEGACY-STATE-TENANT', 'USD', DATE '2024-01-01',
                 'balanced', 'medium',
                 'discretionary', 'SGPB', 'LEGACY-CLIENT-2', 'ACTIVE', false),
                ('LIVE-STATE', 'LEGACY-STATE-TENANT', 'USD', DATE '2024-01-01',
                 'balanced', 'medium',
                 'discretionary', 'SGPB', 'LEGACY-CLIENT-3', 'ACTIVE', false)
            """
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO instruments (security_id, name, isin, currency, product_type, asset_class)
            VALUES
                ('LEGACY-SEC-1', 'Legacy snapshot', 'LEGACY-ISIN-1', 'USD', 'Stock', 'Equity'),
                ('LEGACY-SEC-2', 'Legacy history', 'LEGACY-ISIN-2', 'USD', 'Stock', 'Equity'),
                ('LEGACY-SEC-3', 'Existing state', 'LEGACY-ISIN-3', 'USD', 'Stock', 'Equity')
            """
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO daily_position_snapshots (
                portfolio_id, security_id, date, epoch, quantity, cost_basis
            ) VALUES
                ('LEGACY-SNAPSHOT', ' LEGACY-SEC-1 ', DATE '2026-01-10', 0, 5, 50),
                ('LIVE-STATE', 'LEGACY-SEC-3', DATE '2026-01-12', 3, 7, 70)
            """
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            ) VALUES (
                'LEGACY-TXN-2', 'LEGACY-HISTORY', 'LEGACY-SEC-2', 'LEGACY-SEC-2',
                'BUY', 4, 10, 40, 'USD', 'USD', TIMESTAMPTZ '2026-01-05 00:00:00+00'
            )
            """
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO position_history (
                portfolio_id, security_id, transaction_id, position_date,
                epoch, quantity, cost_basis
            ) VALUES (
                'LEGACY-HISTORY', 'LEGACY-SEC-2', 'LEGACY-TXN-2', DATE '2026-01-05',
                0, 4, 40
            )
            """
        )
    )
    await async_db_session.execute(
        text(
            """
            INSERT INTO position_state (
                portfolio_id, security_id, epoch, watermark_date, status
            ) VALUES ('LIVE-STATE', 'LEGACY-SEC-3', 3, DATE '2026-01-12', 'CURRENT')
            """
        )
    )

    connection = await async_db_session.connection()
    await _apply_backfill(migration, connection)
    await _apply_backfill(migration, connection)

    rows = (
        (
            await async_db_session.execute(
                text(
                    """
                SELECT portfolio_id, security_id, epoch, watermark_date, status
                FROM position_state
                WHERE portfolio_id IN ('LEGACY-SNAPSHOT', 'LEGACY-HISTORY', 'LIVE-STATE')
                ORDER BY portfolio_id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    assert [dict(row) for row in rows] == [
        {
            "portfolio_id": "LEGACY-HISTORY",
            "security_id": "LEGACY-SEC-2",
            "epoch": 0,
            "watermark_date": date(2026, 1, 4),
            "status": "REPROCESSING",
        },
        {
            "portfolio_id": "LEGACY-SNAPSHOT",
            "security_id": "LEGACY-SEC-1",
            "epoch": 0,
            "watermark_date": date(2026, 1, 10),
            "status": "SNAPSHOT_ONLY",
        },
        {
            "portfolio_id": "LIVE-STATE",
            "security_id": "LEGACY-SEC-3",
            "epoch": 3,
            "watermark_date": date(2026, 1, 12),
            "status": "CURRENT",
        },
    ]

    open_positions = await valuation_repository.ValuationRepository(
        async_db_session
    ).get_all_open_positions()
    assert sorted(open_positions, key=lambda row: (row["portfolio_id"], row["security_id"])) == [
        {"portfolio_id": "LEGACY-SNAPSHOT", "security_id": "LEGACY-SEC-1"},
        {"portfolio_id": "LIVE-STATE", "security_id": "LEGACY-SEC-3"},
    ]

    repo = valuation_repository.ValuationRepository(async_db_session)
    lagging_states = await repo.get_lagging_states(date(2026, 1, 13), limit=10)
    backfill_states = await repo.get_states_needing_backfill(date(2026, 1, 13), limit=10)
    assert ("LEGACY-HISTORY", "REPROCESSING") in {
        (state.portfolio_id, state.status) for state in lagging_states
    }
    assert ("LEGACY-HISTORY", "REPROCESSING") in {
        (state.portfolio_id, state.status) for state in backfill_states
    }
    assert all(state.portfolio_id != "LEGACY-SNAPSHOT" for state in lagging_states)
    assert all(state.portfolio_id != "LEGACY-SNAPSHOT" for state in backfill_states)
