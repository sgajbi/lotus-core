from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from portfolio_common.config import (
    KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
)
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    FinancialReconciliationRequestedEvent,
    PortfolioAggregationDayCompletedEvent,
    PortfolioDayControlsEvaluatedEvent,
)

from .outbox_event_mapper import pipeline_outbox_event_payload


@dataclass(frozen=True)
class PipelineOutboxMessage:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    topic: str
    payload: dict[str, Any]


def financial_reconciliation_requested_message(
    *,
    event: PortfolioAggregationDayCompletedEvent,
    correlation_id: str | None,
) -> PipelineOutboxMessage:
    reconciliation_event = FinancialReconciliationRequestedEvent(
        portfolio_id=event.portfolio_id,
        business_date=event.aggregation_date,
        epoch=event.epoch,
        correlation_id=correlation_id,
    )
    return PipelineOutboxMessage(
        aggregate_type="FinancialReconciliation",
        aggregate_id=f"{event.portfolio_id}:{event.aggregation_date}:{event.epoch}",
        event_type="FinancialReconciliationRequested",
        topic=KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
        payload=pipeline_outbox_event_payload(reconciliation_event),
    )


def portfolio_day_controls_evaluated_message(
    *,
    event: FinancialReconciliationCompletedEvent,
    stage_status: str,
    controls_blocking: bool,
    correlation_id: str | None,
) -> PipelineOutboxMessage:
    controls_event = PortfolioDayControlsEvaluatedEvent(
        portfolio_id=event.portfolio_id,
        business_date=event.business_date,
        epoch=event.epoch,
        status=stage_status,
        controls_blocking=controls_blocking,
        publish_allowed=not controls_blocking,
        blocking_reconciliation_types=event.blocking_reconciliation_types,
        error_count=event.error_count,
        warning_count=event.warning_count,
        correlation_id=correlation_id,
    )
    return PipelineOutboxMessage(
        aggregate_type="PipelineStage",
        aggregate_id=f"{event.portfolio_id}:{event.business_date}:{event.epoch}",
        event_type="PortfolioDayControlsEvaluated",
        topic=KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
        payload=pipeline_outbox_event_payload(controls_event),
    )
