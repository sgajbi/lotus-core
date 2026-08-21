from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import PortfolioValuationJob
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.operations_support import (
    measure_operations_support_page,
)
from scripts.operations.database_evidence.runtime_fragments import publish_requested_fragments

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")
TARGET_PORTFOLIO = "PLAN-EVIDENCE-OPERATIONS"
NOISE_PORTFOLIO = "PLAN-EVIDENCE-OPERATIONS-NOISE"
REFERENCE_NOW = datetime(2026, 8, 22, 12, tzinfo=UTC)


async def _seed_valuation_jobs(session: AsyncSession, *, count: int) -> None:
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(PortfolioValuationJob),
            [
                {
                    "portfolio_id": (TARGET_PORTFOLIO if sequence < 1_000 else NOISE_PORTFOLIO),
                    "security_id": f"PLAN-OPS-SEC-{sequence:05d}",
                    "valuation_date": date(2026, 1, 1) + timedelta(days=sequence % 200),
                    "epoch": 1,
                    "status": "FAILED",
                    "failure_reason": "representative_failure",
                    "attempt_count": 1,
                    "created_at": REFERENCE_NOW - timedelta(days=2),
                    "updated_at": REFERENCE_NOW - timedelta(days=1, seconds=sequence),
                }
                for sequence in range(start, stop)
            ],
        )
    await session.commit()
    await session.execute(text("ANALYZE portfolio_valuation_jobs"))


async def test_operations_support_page_reports_bounded_plan_posture(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()["operations_support_page"]
    await _seed_valuation_jobs(async_db_session, count=scenario.seed_cardinality)

    result = await measure_operations_support_page(
        async_db_session,
        portfolio_id=TARGET_PORTFOLIO,
        reference_now=REFERENCE_NOW,
        scenario=scenario,
    )
    publish_requested_fragments((result,))

    seeded_jobs = await async_db_session.scalar(
        text("SELECT count(*) FROM portfolio_valuation_jobs")
    )
    assert seeded_jobs == scenario.seed_cardinality
