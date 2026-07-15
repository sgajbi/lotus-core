"""Prove bounded Prometheus labels for aggregation queue lifecycle outcomes."""

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobBatchResult,
    ExpiredAggregationJobRecovery,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    aggregation_scheduler_adapters,
)


def test_scheduler_metrics_map_recovery_claim_and_processing_outcomes(monkeypatch) -> None:
    observed: list[tuple[str, str, str, int]] = []
    monkeypatch.setattr(
        aggregation_scheduler_adapters,
        "observe_control_queue_outcome",
        lambda queue, stage, outcome, count=1: observed.append((queue, stage, outcome, count)),
    )
    sink = aggregation_scheduler_adapters.PrometheusAggregationSchedulerMetricsSink()

    sink.observe_recovery(ExpiredAggregationJobRecovery(requeued_count=2, failed_count=1))
    sink.observe_claimed(3)
    sink.observe_processed(
        AggregationJobBatchResult(
            complete_count=4,
            requeued_count=1,
            lost_ownership_count=2,
            failed_count=1,
            execution_error_count=1,
        )
    )

    assert observed == [
        ("aggregation", "lease_recovery", "requeued", 2),
        ("aggregation", "lease_recovery", "failed", 1),
        ("aggregation", "claim", "claimed", 3),
        ("aggregation", "processing", "complete", 4),
        ("aggregation", "processing", "requeued", 1),
        ("aggregation", "processing", "lost_ownership", 2),
        ("aggregation", "processing", "failed", 1),
        ("aggregation", "processing", "execution_error", 1),
    ]
