from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import PortfolioValuationJob
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.runtime_fragments import publish_requested_fragments
from scripts.operations.database_evidence.valuation_stale_recovery import (
    measure_valuation_stale_recovery,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")
REFERENCE_NOW = datetime(2020, 1, 1, 12, tzinfo=UTC)


async def _seed_stale_valuation_jobs(session: AsyncSession, *, count: int) -> None:
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(PortfolioValuationJob),
            [
                {
                    "portfolio_id": f"PLAN-STALE-PORT-{sequence % 100:03d}",
                    "security_id": f"PLAN-STALE-SEC-{sequence:05d}",
                    "valuation_date": date(2026, 1, 1) + timedelta(days=sequence % 200),
                    "epoch": 1,
                    "status": "PROCESSING",
                    "attempt_count": 1,
                    "valuation_lease_owner": "database-hot-path-evidence",
                    "valuation_claim_token": f"{sequence:032x}",
                    "valuation_lease_expires_at": REFERENCE_NOW - timedelta(hours=1),
                    "created_at": REFERENCE_NOW - timedelta(days=2),
                    "updated_at": REFERENCE_NOW - timedelta(hours=2),
                }
                for sequence in range(start, stop)
            ],
        )
    await session.commit()
    await session.execute(text("ANALYZE portfolio_valuation_jobs"))
    await session.commit()


async def _valuation_authority_snapshot(
    session: AsyncSession,
) -> list[tuple[object, ...]]:
    rows = await session.execute(
        select(
            PortfolioValuationJob.id,
            PortfolioValuationJob.status,
            PortfolioValuationJob.requeue_requested,
            PortfolioValuationJob.failure_reason,
            PortfolioValuationJob.attempt_count,
            PortfolioValuationJob.claimed_readiness_outbox_id,
            PortfolioValuationJob.valuation_lease_owner,
            PortfolioValuationJob.valuation_claim_token,
            PortfolioValuationJob.valuation_lease_expires_at,
            PortfolioValuationJob.updated_at,
        ).order_by(PortfolioValuationJob.id)
    )
    return [tuple(row) for row in rows]


async def test_valuation_stale_recovery_publishes_rollback_safe_evidence(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenarios = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()
    seed_cardinality = scenarios["valuation_stale_scan"].seed_cardinality
    assert scenarios["valuation_stale_reset"].seed_cardinality == seed_cardinality
    await _seed_stale_valuation_jobs(async_db_session, count=seed_cardinality)
    authority_before = await _valuation_authority_snapshot(async_db_session)
    reset_job_ids = tuple(int(row[0]) for row in authority_before)[
        : scenarios["valuation_stale_reset"].max_root_actual_rows
    ]
    await async_db_session.rollback()

    scan_result, reset_result = await measure_valuation_stale_recovery(
        async_db_session,
        scan_scenario=scenarios["valuation_stale_scan"],
        reset_scenario=scenarios["valuation_stale_reset"],
        reset_job_ids=reset_job_ids,
    )
    publish_requested_fragments((reset_result, scan_result))

    verification_sessions = async_sessionmaker(
        bind=async_db_session.bind,
        expire_on_commit=False,
    )
    async with verification_sessions() as verification_session:
        authority_after = await _valuation_authority_snapshot(verification_session)
    assert authority_after == authority_before
    assert len(authority_after) == seed_cardinality
