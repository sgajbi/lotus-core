from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import PipelineStageState
from portfolio_common.domain.holdings_reconciliation import HoldingsReconciliationScope
from portfolio_common.reconciliation_quality import FINANCIAL_RECONCILIATION_STAGE
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.core_snapshot_sources import (
    SqlAlchemyCoreSnapshotSourceReader,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]


async def test_core_snapshot_control_read_is_exact_and_set_based(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    selected_date = date(2026, 4, 10)
    selected_updated_at = datetime(2026, 4, 10, 3, tzinfo=UTC)
    async_db_session.add_all(
        [
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P1:2026-04-10",
                portfolio_id="P1",
                business_date=selected_date,
                epoch=4,
                status="COMPLETED",
                updated_at=selected_updated_at,
            ),
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P1:2026-04-10:old",
                portfolio_id="P1",
                business_date=selected_date,
                epoch=3,
                status="FAILED",
            ),
            PipelineStageState(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id="reconciliation:P2:2026-04-10",
                portfolio_id="P2",
                business_date=selected_date,
                epoch=4,
                status="FAILED",
            ),
        ]
    )
    await async_db_session.commit()

    controls = await SqlAlchemyCoreSnapshotSourceReader(
        async_db_session
    ).get_financial_reconciliation_controls(
        portfolio_id="P1",
        scopes=(
            HoldingsReconciliationScope(
                business_date=selected_date,
                epoch=4,
                latest_evidence_timestamp=datetime(2026, 4, 10, 2, tzinfo=UTC),
                source_row_count=100_000,
            ),
        ),
    )

    assert len(controls) == 1
    assert controls[0].business_date == selected_date
    assert controls[0].epoch == 4
    assert controls[0].status == "COMPLETED"
    assert controls[0].updated_at == selected_updated_at
