"""Prove atomic transaction-readiness claims against PostgreSQL."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import PipelineStageState
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_readiness import (  # noqa: E501
    SqlAlchemyTransactionStageRepository,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)

pytestmark = pytest.mark.asyncio

STAGE_NAME = "TRANSACTION_PROCESSING"
PORTFOLIO_ID = "PB-READINESS-001"
TRANSACTION_ID = "TX-READINESS-001"


async def _claim(
    repository: SqlAlchemyTransactionStageRepository,
    *,
    portfolio_id: str = PORTFOLIO_ID,
    epoch: int = 4,
):
    await repository.acquire_stage_lock(
        stage_name=STAGE_NAME,
        portfolio_id=portfolio_id,
        transaction_id=TRANSACTION_ID,
    )
    return await repository.claim_processed_stage(
        stage_name=STAGE_NAME,
        transaction_id=TRANSACTION_ID,
        portfolio_id=portfolio_id,
        security_id="SEC-READINESS-001",
        business_date=date(2026, 8, 10),
        epoch=epoch,
    )


async def test_claim_is_complete_duplicate_neutral_and_epoch_monotonic(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = SqlAlchemyTransactionStageRepository(async_db_session)

    first = await _claim(repository)
    duplicate = await _claim(repository)
    stale = await _claim(repository, epoch=3)
    next_epoch = await _claim(repository, epoch=5)
    await async_db_session.commit()

    assert first is not None
    assert first.status == "COMPLETED"
    assert first.cost_event_seen is True
    assert duplicate is None
    assert stale is None
    assert next_epoch is not None
    rows = list(
        (
            await async_db_session.scalars(
                select(PipelineStageState)
                .where(
                    PipelineStageState.stage_name == STAGE_NAME,
                    PipelineStageState.transaction_id == TRANSACTION_ID,
                )
                .order_by(PipelineStageState.epoch)
            )
        ).all()
    )
    assert [(row.epoch, row.status) for row in rows] == [
        (4, "COMPLETED"),
        (5, "COMPLETED"),
    ]


async def test_claim_rejects_cross_portfolio_stage_identity_collision(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = SqlAlchemyTransactionStageRepository(async_db_session)
    assert await _claim(repository) is not None

    with pytest.raises(ValueError, match="existing=PB-READINESS-001 incoming=PB-OTHER"):
        await _claim(repository, portfolio_id="PB-OTHER")


async def test_completed_legacy_stage_refreshes_flags_without_reclaiming_authority(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    ready_emitted_at = datetime(2026, 8, 10, 1, 2, 3, tzinfo=UTC)
    async_db_session.add(
        PipelineStageState(
            stage_name=STAGE_NAME,
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            security_id="SEC-READINESS-OLD",
            business_date=date(2026, 8, 9),
            epoch=4,
            status="COMPLETED",
            cost_event_seen=False,
            cashflow_event_seen=False,
            ready_emitted_at=ready_emitted_at,
        )
    )
    await async_db_session.commit()

    assert await _claim(SqlAlchemyTransactionStageRepository(async_db_session)) is None
    await async_db_session.commit()
    stage = await async_db_session.scalar(
        select(PipelineStageState).where(
            PipelineStageState.stage_name == STAGE_NAME,
            PipelineStageState.transaction_id == TRANSACTION_ID,
            PipelineStageState.epoch == 4,
        )
    )

    assert stage is not None
    assert stage.cost_event_seen is True
    assert stage.cashflow_event_seen is True
    assert stage.security_id == "SEC-READINESS-001"
    assert stage.business_date == date(2026, 8, 10)
    assert stage.ready_emitted_at == ready_emitted_at


async def test_waiting_duplicate_observes_committed_completion_after_stage_lock(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    assert async_db_session.bind is not None
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    owner_claimed = asyncio.Event()
    release_owner = asyncio.Event()
    contender_attempted = asyncio.Event()
    contender_acquired = asyncio.Event()
    contender_backend_pid: list[int] = []

    async def own_completion():
        async with session_factory() as session, session.begin():
            claimed = await _claim(SqlAlchemyTransactionStageRepository(session))
            owner_claimed.set()
            await release_owner.wait()
            return claimed

    async def contend_for_completion():
        async with session_factory() as session, session.begin():
            contender_backend_pid.append(int(await session.scalar(text("SELECT pg_backend_pid()"))))
            contender_attempted.set()
            repository = SqlAlchemyTransactionStageRepository(session)
            await repository.acquire_stage_lock(
                stage_name=STAGE_NAME,
                portfolio_id=PORTFOLIO_ID,
                transaction_id=TRANSACTION_ID,
            )
            contender_acquired.set()
            return await repository.claim_processed_stage(
                stage_name=STAGE_NAME,
                transaction_id=TRANSACTION_ID,
                portfolio_id=PORTFOLIO_ID,
                security_id="SEC-READINESS-001",
                business_date=date(2026, 8, 10),
                epoch=4,
            )

    owner_task = asyncio.create_task(own_completion())
    contender_task: asyncio.Task | None = None
    try:
        await wait_for_task_signal(owner_task, owner_claimed, timeout=2)
        contender_task = asyncio.create_task(contend_for_completion())
        await wait_for_task_signal(contender_task, contender_attempted, timeout=2)
        await wait_for_postgres_advisory_lock_wait(
            contender_task,
            session_factory,
            backend_pid=contender_backend_pid[0],
            timeout=2,
        )
        assert contender_acquired.is_set() is False

        release_owner.set()
        owner_result, contender_result = await asyncio.wait_for(
            asyncio.gather(owner_task, contender_task),
            timeout=5,
        )
    finally:
        release_owner.set()
        await cancel_pending_tasks(owner_task, contender_task)

    assert owner_result is not None
    assert contender_acquired.is_set() is True
    assert contender_result is None
