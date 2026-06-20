from decimal import Decimal

from src.services.ingestion_service.app.services.ingestion_operating_band import (
    OperatingBandPolicy,
)
from src.services.ingestion_service.app.services.ingestion_operating_policy import (
    IngestionOperatingPolicyConfig,
    build_operating_policy_config,
    build_operating_policy_response,
)
from src.services.ingestion_service.app.settings import (
    IngestionOperatingBandSettings,
    IngestionRuntimePolicySettings,
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


def test_build_operating_policy_config_maps_runtime_policy_values() -> None:
    runtime_policy = IngestionRuntimePolicySettings(
        replay_max_records_per_request=5000,
        replay_max_backlog_jobs=25,
        dlq_budget_events_per_window=7,
        default_lookback_minutes=45,
        default_failure_rate_threshold=Decimal("0.04"),
        default_queue_latency_threshold_seconds=6.5,
        default_backlog_age_threshold_seconds=240.0,
        reprocessing_worker_poll_interval_seconds=12,
        reprocessing_worker_batch_size=30,
        valuation_scheduler_poll_interval_seconds=40,
        valuation_scheduler_batch_size=125,
        valuation_scheduler_dispatch_rounds=8,
        capacity_assumed_replicas=3,
        replay_isolation_mode="dedicated_workers",
        partition_growth_strategy="pre_shard_large_portfolios",
        calculator_peak_lag_age_seconds={"position": 30, "valuation": 60},
        operating_band=IngestionOperatingBandSettings(
            yellow_backlog_age_seconds=15.0,
            orange_backlog_age_seconds=60.0,
            red_backlog_age_seconds=180.0,
            yellow_dlq_pressure_ratio=Decimal("0.25"),
            orange_dlq_pressure_ratio=Decimal("0.50"),
            red_dlq_pressure_ratio=Decimal("1.0"),
        ),
    )
    operating_band_policy = OperatingBandPolicy(
        yellow_backlog_age_seconds=20.0,
        orange_backlog_age_seconds=90.0,
        red_backlog_age_seconds=240.0,
        yellow_dlq_pressure_ratio=Decimal("0.20"),
        orange_dlq_pressure_ratio=Decimal("0.45"),
        red_dlq_pressure_ratio=Decimal("0.95"),
    )

    config = build_operating_policy_config(
        runtime_policy=runtime_policy,
        operating_band_policy=operating_band_policy,
    )

    assert config.lookback_minutes_default == 45
    assert config.failure_rate_threshold_default == Decimal("0.04")
    assert config.queue_latency_threshold_seconds_default == 6.5
    assert config.backlog_age_threshold_seconds_default == 240.0
    assert config.replay_max_records_per_request == 5000
    assert config.replay_max_backlog_jobs == 25
    assert config.reprocessing_worker_poll_interval_seconds == 12
    assert config.reprocessing_worker_batch_size == 30
    assert config.valuation_scheduler_poll_interval_seconds == 40
    assert config.valuation_scheduler_batch_size == 125
    assert config.valuation_scheduler_dispatch_rounds == 8
    assert config.dlq_budget_events_per_window == 7
    assert config.operating_band_policy == operating_band_policy
    assert config.calculator_peak_lag_age_seconds == {"position": 30, "valuation": 60}
    assert (
        config.calculator_peak_lag_age_seconds is not runtime_policy.calculator_peak_lag_age_seconds
    )
    assert config.replay_isolation_mode == "dedicated_workers"
    assert config.partition_growth_strategy == "pre_shard_large_portfolios"
