"""Transactional outbox adapter for reconciliation completion contracts."""

from __future__ import annotations

from portfolio_common.config import (
    KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC,
)
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioDayControlsEvaluatedEvent,
)
from portfolio_common.outbox_repository import OutboxRepository

from ..domain.reconciliation_control import FinancialReconciliationCompletion


class TransactionalReconciliationCompletionEventStager:
    """Stage existing completion and control events in the caller transaction."""

    def __init__(self, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def stage_reconciliation_completed(
        self,
        completion: FinancialReconciliationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        """Stage the existing reconciliation-completed contract unchanged."""

        event = FinancialReconciliationCompletedEvent(
            portfolio_id=completion.portfolio_id,
            business_date=completion.business_date,
            epoch=completion.epoch,
            outcome_status=completion.outcome_status,
            reconciliation_types=list(completion.reconciliation_types),
            blocking_reconciliation_types=list(completion.blocking_reconciliation_types),
            run_ids=dict(completion.run_ids),
            error_count=completion.error_count,
            warning_count=completion.warning_count,
            requested_by=completion.requested_by,
            trigger_stage=completion.trigger_stage,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="FinancialReconciliation",
            aggregate_id=self._aggregate_id(completion),
            event_type="FinancialReconciliationCompleted",
            topic=KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC,
            payload=outbox_event_payload(event),
            correlation_id=correlation_id,
        )

    async def stage_controls_evaluated(
        self,
        completion: FinancialReconciliationCompletion,
        *,
        status: str,
        controls_blocking: bool,
        correlation_id: str | None,
    ) -> None:
        """Stage the existing controls-evaluated contract unchanged."""

        event = PortfolioDayControlsEvaluatedEvent(
            portfolio_id=completion.portfolio_id,
            business_date=completion.business_date,
            epoch=completion.epoch,
            status=status,
            controls_blocking=controls_blocking,
            publish_allowed=not controls_blocking,
            blocking_reconciliation_types=list(completion.blocking_reconciliation_types),
            error_count=completion.error_count,
            warning_count=completion.warning_count,
            correlation_id=correlation_id,
        )
        await self._outbox_repository.create_outbox_event(
            aggregate_type="PipelineStage",
            aggregate_id=self._aggregate_id(completion),
            event_type="PortfolioDayControlsEvaluated",
            topic=KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
            payload=outbox_event_payload(event),
            correlation_id=correlation_id,
        )

    @staticmethod
    def _aggregate_id(completion: FinancialReconciliationCompletion) -> str:
        """Preserve the existing portfolio-day-epoch aggregate identity."""

        return f"{completion.portfolio_id}:{completion.business_date}:{completion.epoch}"
