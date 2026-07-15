"""Transactional outbox adapter for portfolio aggregation completion."""

from __future__ import annotations

from portfolio_common.config import (
    KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
)
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import (
    FinancialReconciliationRequestedEvent,
    PortfolioAggregationDayCompletedEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..domain.aggregation_records import PortfolioAggregationCompletion


class TransactionalAggregationCompletionEventStager:
    """Stage completion and reconciliation events through one outbox transaction."""

    def __init__(self, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def stage_completion(
        self,
        completion: PortfolioAggregationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        """Preserve existing event identities while removing the pipeline relay."""

        completed_event = PortfolioAggregationDayCompletedEvent(
            portfolio_id=completion.portfolio_id,
            aggregation_date=completion.aggregation_date,
            epoch=completion.epoch,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="PortfolioAggregationStage",
            aggregate_id=(
                f"{completion.portfolio_id}:{completion.aggregation_date}:{completion.epoch}"
            ),
            event_type="PortfolioAggregationDayCompleted",
            topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
            payload=outbox_event_payload(completed_event),
            correlation_id=correlation_id,
        )

        reconciliation_event = FinancialReconciliationRequestedEvent(
            portfolio_id=completion.portfolio_id,
            business_date=completion.aggregation_date,
            epoch=completion.epoch,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="FinancialReconciliation",
            aggregate_id=(
                f"{completion.portfolio_id}:{completion.aggregation_date}:{completion.epoch}"
            ),
            event_type="FinancialReconciliationRequested",
            topic=KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
            payload=outbox_event_payload(reconciliation_event),
            correlation_id=correlation_id,
        )
