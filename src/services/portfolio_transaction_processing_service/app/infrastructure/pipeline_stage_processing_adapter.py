"""Bridge rebuilt transaction epochs to the existing pipeline readiness service."""

from __future__ import annotations

from src.services.pipeline_orchestrator_service.app.services.pipeline_orchestrator_service import (
    PipelineOrchestratorService,
)

from ..domain import BookedTransaction
from .legacy_transaction_event_mapper import to_transaction_event


class PipelineStageProcessingCompatibilityAdapter:
    """Register rebuilt cost-stage completion without legacy topic replay."""

    def __init__(self, service: PipelineOrchestratorService) -> None:
        self._service = service

    async def register_processed_transactions(
        self,
        transactions: tuple[BookedTransaction, ...],
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None:
        for transaction in transactions:
            await self._service.register_processed_transaction(
                to_transaction_event(
                    transaction,
                    correlation_id=correlation_id,
                    traceparent=traceparent,
                ),
                correlation_id,
            )
