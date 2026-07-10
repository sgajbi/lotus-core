from __future__ import annotations

from portfolio_common.outbox_repository import OutboxRepository

from src.services.calculators.cost_calculator_service.app.cost_calculation_processor import (
    CostCalculationEventProcessor,
    CostCalculationWorkflow,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
)

from ..domain import BookedTransaction
from ..ports import CostProcessingResult
from .legacy_transaction_event_mapper import to_booked_transaction, to_transaction_event


class CostProcessingCompatibilityAdapter:
    """Run the current cost policy inside the combined caller-owned unit of work."""

    def __init__(
        self,
        *,
        workflow: CostCalculationWorkflow,
        repository: CostCalculatorRepository,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._processor = CostCalculationEventProcessor(workflow)
        self._repository = repository
        self._outbox_repository = outbox_repository

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CostProcessingResult:
        event = to_transaction_event(
            transaction,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
        stage_result = await self._processor.stage_valid_event(
            event=event,
            correlation_id=correlation_id or "",
            repo=self._repository,
            outbox_repo=self._outbox_repository,
        )
        return CostProcessingResult(
            processed_transactions=tuple(
                to_booked_transaction(item) for item in stage_result.emitted_events
            ),
            instrument_update_count=stage_result.instrument_event_count,
        )
