from dataclasses import dataclass
from datetime import date

from portfolio_common.config import (
    KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
)
from portfolio_common.events import (
    FinancialReconciliationCompletedEvent,
    PortfolioAggregationDayCompletedEvent,
)

from src.services.pipeline_orchestrator_service.app.adapters.pipeline_event_factory import (
    financial_reconciliation_requested_message,
    portfolio_day_controls_evaluated_message,
    portfolio_day_ready_for_valuation_message,
    transaction_processing_completed_message,
)


@dataclass
class _Stage:
    transaction_id: str = "TXN-PIPE-1"
    portfolio_id: str = "PORT-1"
    security_id: str | None = "SEC-1"
    business_date: date = date(2026, 3, 7)
    epoch: int = 2


def test_transaction_processing_completed_message_preserves_topic_and_payload() -> None:
    message = transaction_processing_completed_message(
        stage=_Stage(),
        readiness_reason="cost_and_cashflow_completed",
        correlation_id="corr-1",
    )

    assert message.aggregate_type == "PipelineStage"
    assert message.aggregate_id == "PORT-1:TXN-PIPE-1:2"
    assert message.event_type == "TransactionProcessingCompleted"
    assert message.topic == KAFKA_TRANSACTION_PROCESSING_READY_TOPIC
    assert message.payload["transaction_id"] == "TXN-PIPE-1"
    assert message.payload["stage_name"] == "TRANSACTION_PROCESSING"
    assert message.payload["readiness_reason"] == "cost_and_cashflow_completed"
    assert message.payload["correlation_id"] == "corr-1"


def test_valuation_readiness_message_preserves_topic_and_payload() -> None:
    message = portfolio_day_ready_for_valuation_message(
        stage=_Stage(),
        readiness_reason="cost_completed_non_cashflow",
        correlation_id="corr-2",
    )

    assert message is not None
    assert message.aggregate_type == "ValuationReadiness"
    assert message.aggregate_id == "PORT-1:SEC-1:2026-03-07:2"
    assert message.event_type == "PortfolioDayReadyForValuation"
    assert message.topic == KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC
    assert message.payload["security_id"] == "SEC-1"
    assert message.payload["readiness_reason"] == "cost_completed_non_cashflow"


def test_valuation_readiness_message_is_skipped_without_security_id() -> None:
    assert (
        portfolio_day_ready_for_valuation_message(
            stage=_Stage(security_id=None),
            readiness_reason="cost_and_cashflow_completed",
            correlation_id="corr-3",
        )
        is None
    )


def test_reconciliation_requested_message_preserves_topic_and_payload() -> None:
    event = PortfolioAggregationDayCompletedEvent(
        portfolio_id="PORT-1",
        aggregation_date=date(2026, 3, 7),
        epoch=2,
        correlation_id="corr-4",
    )

    message = financial_reconciliation_requested_message(
        event=event,
        correlation_id="corr-4",
    )

    assert message.aggregate_type == "FinancialReconciliation"
    assert message.aggregate_id == "PORT-1:2026-03-07:2"
    assert message.event_type == "FinancialReconciliationRequested"
    assert message.topic == KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC
    assert message.payload["reconciliation_types"] == [
        "transaction_cashflow",
        "position_valuation",
        "timeseries_integrity",
    ]
    assert message.payload["correlation_id"] == "corr-4"


def test_controls_evaluated_message_preserves_topic_and_blocking_payload() -> None:
    event = FinancialReconciliationCompletedEvent(
        portfolio_id="PORT-1",
        business_date=date(2026, 3, 7),
        epoch=2,
        outcome_status="REQUIRES_REPLAY",
        reconciliation_types=["transaction_cashflow"],
        blocking_reconciliation_types=["transaction_cashflow"],
        run_ids={"transaction_cashflow": "recon-tx"},
        error_count=1,
        warning_count=0,
        correlation_id="corr-5",
    )

    message = portfolio_day_controls_evaluated_message(
        event=event,
        stage_status="REQUIRES_REPLAY",
        controls_blocking=True,
        correlation_id="corr-5",
    )

    assert message.aggregate_type == "PipelineStage"
    assert message.aggregate_id == "PORT-1:2026-03-07:2"
    assert message.event_type == "PortfolioDayControlsEvaluated"
    assert message.topic == KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC
    assert message.payload["status"] == "REQUIRES_REPLAY"
    assert message.payload["controls_blocking"] is True
    assert message.payload["publish_allowed"] is False
    assert message.payload["blocking_reconciliation_types"] == ["transaction_cashflow"]
