from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import PortfolioValuationJob
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.runtime_fragments import publish_requested_fragments
from scripts.operations.database_evidence.valuation_claim import measure_valuation_job_claim

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")


async def _seed_valuation_claims(session: AsyncSession, *, count: int) -> None:
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(PortfolioValuationJob),
            [
                {
                    "portfolio_id": f"PLAN-CLAIM-PORT-{sequence % 100:03d}",
                    "security_id": f"PLAN-CLAIM-SEC-{sequence:05d}",
                    "valuation_date": date(2026, 1, 1) + timedelta(days=sequence % 200),
                    "epoch": 1,
                    "status": "PENDING",
                }
                for sequence in range(start, stop)
            ],
        )
    await session.commit()
    await session.execute(text("ANALYZE portfolio_valuation_jobs"))
    await session.commit()


async def _claim_authority_snapshot(session: AsyncSession) -> list[tuple[object, ...]]:
    rows = await session.execute(
        select(
            PortfolioValuationJob.id,
            PortfolioValuationJob.status,
            PortfolioValuationJob.requeue_requested,
            PortfolioValuationJob.claimed_readiness_outbox_id,
            PortfolioValuationJob.valuation_lease_owner,
            PortfolioValuationJob.valuation_claim_token,
            PortfolioValuationJob.valuation_lease_expires_at,
            PortfolioValuationJob.updated_at,
            PortfolioValuationJob.attempt_count,
        ).order_by(PortfolioValuationJob.id)
    )
    return [tuple(row) for row in rows]


async def test_valuation_claim_plan_is_bounded_indexed_and_rollback_safe(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()["valuation_job_claim"]
    await _seed_valuation_claims(async_db_session, count=scenario.seed_cardinality)
    authority_before = await _claim_authority_snapshot(async_db_session)
    await async_db_session.rollback()

    result = await measure_valuation_job_claim(async_db_session, scenario=scenario)
    publish_requested_fragments((result,))
    verification_sessions = async_sessionmaker(
        bind=async_db_session.bind,
        expire_on_commit=False,
    )
    async with verification_sessions() as verification_session:
        authority_after = await _claim_authority_snapshot(verification_session)
    pending_count = await async_db_session.scalar(
        select(func.count()).where(PortfolioValuationJob.status == "PENDING")
    )
    processing_count = await async_db_session.scalar(
        select(func.count()).where(PortfolioValuationJob.status == "PROCESSING")
    )
    assert pending_count == scenario.seed_cardinality
    assert processing_count == 0
    assert authority_after == authority_before
