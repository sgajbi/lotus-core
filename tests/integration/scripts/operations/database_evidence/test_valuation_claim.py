from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import PortfolioValuationJob
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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


async def test_valuation_claim_plan_is_bounded_indexed_and_rollback_safe(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()["valuation_job_claim"]
    await _seed_valuation_claims(async_db_session, count=scenario.seed_cardinality)

    result = await measure_valuation_job_claim(async_db_session, scenario=scenario)
    publish_requested_fragments((result,))

    assert result.status == "failed", result
    assert result.root_actual_rows == scenario.max_root_actual_rows
    assert result.rows_examined <= scenario.max_rows_examined
    assert result.index_names
    assert "WindowAgg" not in result.node_types
    assert result.sequential_scan_relations == ("portfolio_valuation_jobs",)
    assert "prohibited_node_type:Seq Scan" in result.violations
    pending_count = await async_db_session.scalar(
        select(func.count()).where(PortfolioValuationJob.status == "PENDING")
    )
    processing_count = await async_db_session.scalar(
        select(func.count()).where(PortfolioValuationJob.status == "PROCESSING")
    )
    assert pending_count == scenario.seed_cardinality
    assert processing_count == 0
