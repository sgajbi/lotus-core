from __future__ import annotations

from typing import Protocol

from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_calculator.app.core import position_logic
from src.services.calculators.position_calculator.app.repositories import position_repository

from ..domain import BookedTransaction
from ..ports import PositionProcessingResult
from .legacy_transaction_event_mapper import to_transaction_event


class PositionStagingWorkflow(Protocol):
    async def calculate(
        self,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: position_repository.PositionRepository,
        position_state_repo: PositionStateRepository,
        outbox_repo: OutboxRepository,
    ) -> position_logic.PositionCalculationResult: ...


class CombinedPositionCalculationWorkflow:
    """Rebuild backdated position state inside the caller-owned transaction."""

    @staticmethod
    async def calculate(
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: position_repository.PositionRepository,
        position_state_repo: PositionStateRepository,
        outbox_repo: OutboxRepository,
    ) -> position_logic.PositionCalculationResult:
        return await position_logic.PositionCalculator.calculate(
            event=event,
            db_session=db_session,
            repo=repo,
            position_state_repo=position_state_repo,
            outbox_repo=outbox_repo,
            backdated_handling=position_logic.BackdatedPositionHandling.REBUILD_INLINE,
        )


class PositionProcessingCompatibilityAdapter:
    """Run current position and replay policy inside the combined unit of work."""

    def __init__(
        self,
        *,
        db_session: AsyncSession,
        repository: position_repository.PositionRepository,
        position_state_repository: PositionStateRepository,
        outbox_repository: OutboxRepository,
        workflow: PositionStagingWorkflow = CombinedPositionCalculationWorkflow,
    ) -> None:
        self._db_session = db_session
        self._repository = repository
        self._position_state_repository = position_state_repository
        self._outbox_repository = outbox_repository
        self._workflow = workflow

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> PositionProcessingResult:
        stage_result = await self._workflow.calculate(
            event=to_transaction_event(
                transaction,
                correlation_id=correlation_id,
                traceparent=traceparent,
            ),
            db_session=self._db_session,
            repo=self._repository,
            position_state_repo=self._position_state_repository,
            outbox_repo=self._outbox_repository,
        )
        return PositionProcessingResult(
            position_record_count=stage_result.position_record_count,
            replay_queued=stage_result.replay_queued,
        )
