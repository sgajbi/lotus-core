from __future__ import annotations

from typing import Protocol

from portfolio_common.events import TransactionEvent
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_calculator.app.core import position_logic
from src.services.calculators.position_calculator.app.repositories import position_repository

from ..domain import BookedTransaction
from ..ports import PositionProcessingResult
from .legacy_transaction_event_mapper import to_booked_transaction, to_transaction_event


class PositionStagingWorkflow(Protocol):
    async def calculate(
        self,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: position_repository.PositionRepository,
        position_state_repo: PositionStateRepository,
        rebuild_existing: bool = False,
    ) -> position_logic.PositionCalculationResult: ...


class CombinedPositionCalculationWorkflow:
    """Rebuild backdated position state inside the caller-owned transaction."""

    @staticmethod
    async def calculate(
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: position_repository.PositionRepository,
        position_state_repo: PositionStateRepository,
        rebuild_existing: bool = False,
    ) -> position_logic.PositionCalculationResult:
        return await position_logic.PositionCalculator.calculate(
            event=event,
            db_session=db_session,
            repo=repo,
            position_state_repo=position_state_repo,
            rebuild_existing=rebuild_existing,
        )


class PositionProcessingCompatibilityAdapter:
    """Run current position and replay policy inside the combined unit of work."""

    def __init__(
        self,
        *,
        db_session: AsyncSession,
        repository: position_repository.PositionRepository,
        position_state_repository: PositionStateRepository,
        workflow: PositionStagingWorkflow = CombinedPositionCalculationWorkflow,
    ) -> None:
        self._db_session = db_session
        self._repository = repository
        self._position_state_repository = position_state_repository
        self._workflow = workflow

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
        rebuild_existing: bool = False,
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
            rebuild_existing=rebuild_existing,
        )
        return PositionProcessingResult(
            position_record_count=stage_result.position_record_count,
            replay_queued=False,
            cashflow_rebuild_transactions=tuple(
                to_booked_transaction(event) for event in stage_result.rebuilt_events
            ),
        )
