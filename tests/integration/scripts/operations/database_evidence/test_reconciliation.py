from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import PipelineStageState
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.reconciliation import (
    measure_reconciliation_estate_scan,
)
from src.services.query_service.app.application.holdings_reconciliation import (
    HoldingsReconciliationScope,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")
TARGET_PORTFOLIO = "PLAN-EVIDENCE-RECON"
NOISE_PORTFOLIO = "PLAN-EVIDENCE-RECON-NOISE"
BASE_DATE = date(2020, 1, 1)


async def _seed_reconciliation_controls(session: AsyncSession, *, count: int) -> None:
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(PipelineStageState),
            [
                {
                    "stage_name": "FINANCIAL_RECONCILIATION",
                    "transaction_id": f"PLAN-RECON-{sequence:05d}",
                    "portfolio_id": (TARGET_PORTFOLIO if sequence < 1_000 else NOISE_PORTFOLIO),
                    "business_date": BASE_DATE + timedelta(days=sequence),
                    "epoch": sequence + 1,
                    "status": "COMPLETED",
                }
                for sequence in range(start, stop)
            ],
        )
    await session.commit()
    await session.execute(text("ANALYZE pipeline_stage_state"))


async def test_reconciliation_control_scan_is_bounded_and_index_backed(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    scenario = load_hot_path_scenario_catalog(CATALOG_PATH).by_id()["reconciliation_estate_scan"]
    await _seed_reconciliation_controls(async_db_session, count=scenario.seed_cardinality)
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    scopes = tuple(
        HoldingsReconciliationScope(
            business_date=BASE_DATE + timedelta(days=sequence),
            epoch=sequence + 1,
            latest_evidence_timestamp=observed_at,
            source_row_count=1,
        )
        for sequence in range(scenario.max_root_actual_rows)
    )

    result = await measure_reconciliation_estate_scan(
        async_db_session,
        portfolio_id=TARGET_PORTFOLIO,
        scopes=scopes,
        scenario=scenario,
    )

    assert result.status == "passed", result
    assert result.root_actual_rows == scenario.max_root_actual_rows
    assert result.index_names
    assert result.sequential_scan_relations == ()
