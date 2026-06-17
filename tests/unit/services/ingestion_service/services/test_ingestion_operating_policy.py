from decimal import Decimal

from src.services.ingestion_service.app.services.ingestion_operating_band import (
    OperatingBandPolicy,
)
from src.services.ingestion_service.app.services.ingestion_operating_policy import (
    IngestionOperatingPolicyConfig,
    build_operating_policy_response,
)


def _policy_config() -> IngestionOperatingPolicyConfig:
    return IngestionOperatingPolicyConfig(
        lookback_minutes_default=60,
        failure_rate_threshold_default=Decimal("0.03"),
        queue_latency_threshold_seconds_default=5.0,
        backlog_age_threshold_seconds_default=300.0,
        replay_max_records_per_request=0,
        replay_max_backlog_jobs=100,
        reprocessing_worker_poll_interval_seconds=10,
        reprocessing_worker_batch_size=0,
        valuation_scheduler_poll_interval_seconds=30,
        valuation_scheduler_batch_size=100,
        valuation_scheduler_dispatch_rounds=10,
        dlq_budget_events_per_window=10,
        operating_band_policy=OperatingBandPolicy(
            yellow_backlog_age_seconds=15.0,
            orange_backlog_age_seconds=60.0,
            red_backlog_age_seconds=180.0,
            yellow_dlq_pressure_ratio=Decimal("0.25"),
            orange_dlq_pressure_ratio=Decimal("0.50"),
            red_dlq_pressure_ratio=Decimal("1.0"),
        ),
        calculator_peak_lag_age_seconds={"position": 0, "valuation": 60},
        replay_isolation_mode="unexpected",
        partition_growth_strategy="unexpected",
    )


def test_build_operating_policy_response_normalizes_guardrail_floor_values() -> None:
    response = build_operating_policy_response(_policy_config())

    assert response.replay_max_records_per_request == 1
    assert response.reprocessing_worker_batch_size == 1
    assert response.calculator_peak_lag_age_seconds["position"] == 1
    assert response.replay_isolation_mode == "shared_workers"
    assert response.partition_growth_strategy == "scale_out_only"
    assert len(response.policy_fingerprint) == 16


def test_build_operating_policy_response_fingerprint_is_deterministic() -> None:
    first = build_operating_policy_response(_policy_config())
    second = build_operating_policy_response(_policy_config())

    assert first.policy_fingerprint == second.policy_fingerprint
