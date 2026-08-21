from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_support.postgres_query_plan import plan_index_names, plan_node_types

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

_TARGET_PORTFOLIO = "LATEST-PLAN-TARGET"
_NOISE_PORTFOLIO = "LATEST-PLAN-NOISE"


async def _seed_representative_latest_row_history(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, base_currency, open_date, risk_exposure,
                investment_time_horizon, portfolio_type, booking_center_code,
                client_id, status, is_leverage_allowed
            ) VALUES
                (:target, 'USD', DATE '2024-01-01', 'balanced', 'medium',
                 'discretionary', 'SGPB', 'LATEST-PLAN-CLIENT', 'ACTIVE', false),
                (:noise, 'USD', DATE '2024-01-01', 'balanced', 'medium',
                 'discretionary', 'SGPB', 'LATEST-PLAN-NOISE', 'ACTIVE', false)
            """
        ),
        {"target": _TARGET_PORTFOLIO, "noise": _NOISE_PORTFOLIO},
    )
    await session.execute(
        text(
            """
            INSERT INTO daily_position_snapshots (
                portfolio_id, security_id, date, epoch, quantity, cost_basis
            )
            SELECT
                :target,
                'LATEST-SEC-' || security_no::text,
                DATE '2026-08-21' - date_offset,
                0,
                100,
                1000
            FROM generate_series(1, 500) AS security_no
            CROSS JOIN generate_series(0, 4) AS date_offset
            UNION ALL
            SELECT
                :noise,
                'LATEST-NOISE-' || security_no::text,
                DATE '2026-08-21',
                0,
                100,
                1000
            FROM generate_series(1, 5000) AS security_no
            """
        ),
        {"target": _TARGET_PORTFOLIO, "noise": _NOISE_PORTFOLIO},
    )
    await session.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date
            )
            SELECT
                'LATEST-TXN-' || row_no::text,
                CASE WHEN row_no <= 2500 THEN :target ELSE :noise END,
                CASE
                    WHEN row_no <= 2500
                    THEN 'LATEST-SEC-' || (((row_no - 1) / 5) + 1)::text
                    ELSE 'LATEST-NOISE-' || (row_no - 2500)::text
                END,
                CASE
                    WHEN row_no <= 2500
                    THEN 'LATEST-SEC-' || (((row_no - 1) / 5) + 1)::text
                    ELSE 'LATEST-NOISE-' || (row_no - 2500)::text
                END,
                'BUY', 100, 10, 1000, 'USD', 'USD',
                TIMESTAMPTZ '2026-08-21 00:00:00+00'
                    - ((row_no - 1) % 5) * INTERVAL '1 day'
            FROM generate_series(1, 7500) AS row_no
            """
        ),
        {"target": _TARGET_PORTFOLIO, "noise": _NOISE_PORTFOLIO},
    )
    await session.execute(
        text(
            """
            INSERT INTO position_history (
                portfolio_id, security_id, transaction_id, position_date,
                epoch, quantity, cost_basis
            )
            SELECT
                portfolio_id, security_id, transaction_id,
                transaction_date::date, 0, 100, 1000
            FROM transactions
            WHERE transaction_id LIKE 'LATEST-TXN-%'
            """
        )
    )
    await session.commit()
    await session.execute(text("ANALYZE daily_position_snapshots"))
    await session.execute(text("ANALYZE position_history"))


async def test_latest_snapshot_and_history_queries_use_covering_indexes(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_representative_latest_row_history(async_db_session)

    snapshot_plan = await async_db_session.scalar(
        text(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT DISTINCT ON (portfolio_id, trim(security_id)) id
            FROM daily_position_snapshots
            WHERE portfolio_id = :portfolio_id
            ORDER BY portfolio_id, trim(security_id), date DESC, id DESC
            """
        ),
        {"portfolio_id": _TARGET_PORTFOLIO},
    )
    history_plan = await async_db_session.scalar(
        text(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT DISTINCT ON (trim(security_id)) id
            FROM position_history
            WHERE portfolio_id = :portfolio_id
            ORDER BY trim(security_id), position_date DESC, id DESC
            """
        ),
        {"portfolio_id": _TARGET_PORTFOLIO},
    )
    governed_indexes = set(
        (
            await async_db_session.scalars(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname IN (
                          'ix_daily_snap_port_norm_sec_date_id',
                          'ix_pos_hist_port_norm_sec_date_id'
                      )
                    """
                )
            )
        ).all()
    )

    assert governed_indexes == {
        "ix_daily_snap_port_norm_sec_date_id",
        "ix_pos_hist_port_norm_sec_date_id",
    }
    assert plan_index_names(snapshot_plan)
    assert plan_index_names(history_plan)
    assert "Seq Scan" not in plan_node_types(snapshot_plan)
    assert "Seq Scan" not in plan_node_types(history_plan)
    assert "WindowAgg" not in plan_node_types(snapshot_plan)
    assert "WindowAgg" not in plan_node_types(history_plan)
