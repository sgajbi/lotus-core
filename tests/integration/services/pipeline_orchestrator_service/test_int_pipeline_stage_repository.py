from datetime import date

import pytest
from portfolio_common.database_models import PipelineStageState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.pipeline_orchestrator_service.app.repositories.pipeline_stage_repository import (
    PipelineStageRepository,
)

pytestmark = pytest.mark.asyncio


async def test_upsert_portfolio_control_stage_status_is_monotonic(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)

    first = await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 7),
        epoch=2,
        status="REQUIRES_REPLAY",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    second = await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-1",
        business_date=date(2026, 3, 7),
        epoch=2,
        status="COMPLETED",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    await async_db_session.commit()

    persisted = await async_db_session.scalar(
        select(PipelineStageState).where(PipelineStageState.id == first.id)
    )
    assert first.id == second.id
    assert persisted is not None
    assert persisted.status == "REQUIRES_REPLAY"


async def test_upsert_portfolio_control_stage_status_escalates_to_failed(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)

    await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-2",
        business_date=date(2026, 3, 7),
        epoch=2,
        status="COMPLETED",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    stage = await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-2",
        business_date=date(2026, 3, 7),
        epoch=2,
        status="FAILED",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    await async_db_session.commit()

    assert stage.status == "FAILED"


async def test_get_latest_portfolio_control_stage_epoch_returns_highest_epoch(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)

    await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-3",
        business_date=date(2026, 3, 7),
        epoch=2,
        status="COMPLETED",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    await repo.upsert_portfolio_control_stage_status(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-3",
        business_date=date(2026, 3, 7),
        epoch=4,
        status="COMPLETED",
        source_event_type="portfolio_day.reconciliation.completed",
    )
    await async_db_session.commit()

    latest_epoch = await repo.get_latest_portfolio_control_stage_epoch(
        stage_name="FINANCIAL_RECONCILIATION",
        portfolio_id="PORT-CTRL-3",
        business_date=date(2026, 3, 7),
    )

    assert latest_epoch == 4
