import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from portfolio_common.database_models import OutboxEvent, PipelineStageState
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.pipeline_orchestrator_service.app.repositories.pipeline_stage_repository import (
    PipelineStageRepository,
)
from src.services.pipeline_orchestrator_service.app.services.pipeline_orchestrator_service import (
    PipelineOrchestratorService,
)

pytestmark = pytest.mark.asyncio


def _transaction_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="TXN-PIPE-INT-01",
        portfolio_id="PORT-PIPE-INT-01",
        instrument_id="INST-PIPE-INT-01",
        security_id="SEC-PIPE-INT-01",
        transaction_date=datetime(2025, 8, 22, 9, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        epoch=0,
    )


async def test_emit_if_ready_skips_outbox_after_losing_stage_ownership(
    clean_db, async_db_session: AsyncSession
):
    repo = PipelineStageRepository(async_db_session)
    outbox_repo = OutboxRepository(async_db_session)
    service = PipelineOrchestratorService(repo=repo, outbox_repo=outbox_repo)
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    txn = _transaction_event()
    stage = await repo.upsert_stage_flags(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id=txn.transaction_id,
        portfolio_id=txn.portfolio_id,
        security_id=txn.security_id,
        business_date=txn.transaction_date.date(),
        epoch=txn.epoch or 0,
        source_event_type="processed_transaction",
        cost_event_seen=True,
        cashflow_event_seen=False,
    )
    await async_db_session.commit()
    await async_db_session.refresh(stage)

    original_mark_stage_completed_if_pending = repo.mark_stage_completed_if_pending

    async def mark_stage_completed_with_ownership_loss(stage_state):
        async with session_factory() as session:
            await session.execute(
                update(PipelineStageState)
                .where(PipelineStageState.id == stage_state.id)
                .values(status="COMPLETED", ready_emitted_at=func.now())
            )
            await session.commit()
        return await original_mark_stage_completed_if_pending(stage_state)

    with patch.object(
        repo,
        "mark_stage_completed_if_pending",
        new=mark_stage_completed_with_ownership_loss,
    ):
        await service._emit_if_ready(
            stage,
            correlation_id="corr-pipe-int-01",
        )

    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id.in_(
                        [
                            "PORT-PIPE-INT-01:TXN-PIPE-INT-01:0",
                            "PORT-PIPE-INT-01:SEC-PIPE-INT-01:2025-08-22:0",
                        ]
                    ),
                    OutboxEvent.event_type.in_(
                        [
                            "TransactionProcessingCompleted",
                            "PortfolioDayReadyForValuation",
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    stage = await async_db_session.scalar(
        select(PipelineStageState).where(
            PipelineStageState.stage_name == "TRANSACTION_PROCESSING",
            PipelineStageState.transaction_id == "TXN-PIPE-INT-01",
            PipelineStageState.epoch == 0,
        )
    )

    assert outbox_rows == []
    assert stage is not None
    assert stage.status == "COMPLETED"
    assert stage.ready_emitted_at is not None


async def test_stale_processed_transaction_does_not_create_superseded_epoch_readiness(
    clean_db, async_db_session: AsyncSession
):
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    transaction = _transaction_event()
    async with session_factory() as current_session, session_factory() as stale_session:
        current_service = PipelineOrchestratorService(
            repo=PipelineStageRepository(current_session),
            outbox_repo=OutboxRepository(current_session),
        )
        stale_service = PipelineOrchestratorService(
            repo=PipelineStageRepository(stale_session),
            outbox_repo=OutboxRepository(stale_session),
        )
        await current_service.register_processed_transaction(
            transaction.model_copy(update={"epoch": 1}),
            correlation_id="corr-current-epoch",
        )
        stale_task = asyncio.create_task(
            stale_service.register_processed_transaction(
                transaction,
                correlation_id="corr-stale-epoch",
            )
        )
        await asyncio.sleep(0.1)
        assert stale_task.done() is False

        await current_session.commit()
        await asyncio.wait_for(stale_task, timeout=2)
        await stale_session.commit()

    async with session_factory() as verification_session:
        stale_stage = await verification_session.scalar(
            select(PipelineStageState).where(
                PipelineStageState.stage_name == "TRANSACTION_PROCESSING",
                PipelineStageState.transaction_id == transaction.transaction_id,
                PipelineStageState.epoch == 0,
            )
        )
        readiness_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.event_type.in_(
                        ["TransactionProcessingCompleted", "PortfolioDayReadyForValuation"]
                    ),
                    OutboxEvent.payload["epoch"].as_integer() == 0,
                )
            )
            or 0
        )

    assert stale_stage is None
    assert readiness_count == 0
