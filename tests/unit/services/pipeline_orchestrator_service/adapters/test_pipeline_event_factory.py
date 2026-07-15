from datetime import date

from portfolio_common.config import KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC
from portfolio_common.events import FinancialReconciliationCompletedEvent

from src.services.pipeline_orchestrator_service.app.adapters.pipeline_event_factory import (
    portfolio_day_controls_evaluated_message,
)


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
