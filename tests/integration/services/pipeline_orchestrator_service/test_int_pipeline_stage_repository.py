from datetime import date

import pytest
from portfolio_common.database_models import PipelineStageState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.pipeline_orchestrator_service.app.repositories.pipeline_stage_repository import (
    PipelineStageRepository,
)

pytestmark = pytest.mark.asyncio


async def test_upsert_stage_flags_merges_prerequisite_signals(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)

    first = await repo.upsert_stage_flags(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TXN-INT-1",
        portfolio_id="PORT-INT-1",
        security_id="SEC-INT-1",
        business_date=date(2026, 3, 7),
        epoch=0,
        source_event_type="processed_transaction",
        cost_event_seen=True,
        cashflow_event_seen=False,
    )
    second = await repo.upsert_stage_flags(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TXN-INT-1",
        portfolio_id="PORT-INT-1",
        security_id="SEC-INT-1",
        business_date=date(2026, 3, 7),
        epoch=0,
        source_event_type="cashflows.calculated",
        cost_event_seen=False,
        cashflow_event_seen=True,
    )
    await async_db_session.commit()

    assert first.id == second.id
    assert second.cost_event_seen is True
    assert second.cashflow_event_seen is True
    assert second.status == "PENDING"
    assert second.last_source_event_type == "cashflows.calculated"


async def test_mark_stage_completed_if_pending_is_idempotent(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)
    stage = await repo.upsert_stage_flags(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TXN-INT-2",
        portfolio_id="PORT-INT-2",
        security_id="SEC-INT-2",
        business_date=date(2026, 3, 7),
        epoch=0,
        source_event_type="cashflows.calculated",
        cost_event_seen=True,
        cashflow_event_seen=True,
    )

    first_claim = await repo.mark_stage_completed_if_pending(stage)
    second_claim = await repo.mark_stage_completed_if_pending(stage)
    await async_db_session.commit()

    persisted = await async_db_session.scalar(
        select(PipelineStageState).where(PipelineStageState.id == stage.id)
    )
    assert first_claim is True
    assert second_claim is False
    assert persisted is not None
    assert persisted.status == "COMPLETED"
    assert persisted.ready_emitted_at is not None


async def test_upsert_stage_flags_rejects_cross_portfolio_collision(
    async_db_session: AsyncSession, clean_db
):
    repo = PipelineStageRepository(async_db_session)

    first = await repo.upsert_stage_flags(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TXN-COLLIDE-1",
        portfolio_id="PORT-INT-A",
        security_id="SEC-INT-1",
        business_date=date(2026, 3, 7),
        epoch=0,
        source_event_type="processed_transaction",
        cost_event_seen=True,
        cashflow_event_seen=False,
    )
    with pytest.raises(ValueError, match="Pipeline stage key collision detected"):
        await repo.upsert_stage_flags(
            stage_name="TRANSACTION_PROCESSING",
            transaction_id="TXN-COLLIDE-1",
            portfolio_id="PORT-INT-B",
            security_id="SEC-INT-1",
            business_date=date(2026, 3, 7),
            epoch=0,
            source_event_type="cashflows.calculated",
            cost_event_seen=False,
            cashflow_event_seen=True,
        )
    await async_db_session.commit()
    assert first.id is not None


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
