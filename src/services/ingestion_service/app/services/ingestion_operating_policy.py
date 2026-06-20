from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ..DTOs.ingestion_job_dto import IngestionOpsPolicyResponse
from ..settings import IngestionRuntimePolicySettings
from .ingestion_operating_band import OperatingBandPolicy


@dataclass(frozen=True, slots=True)
class IngestionOperatingPolicyConfig:
    lookback_minutes_default: int
    failure_rate_threshold_default: Decimal
    queue_latency_threshold_seconds_default: float
    backlog_age_threshold_seconds_default: float
    replay_max_records_per_request: int
    replay_max_backlog_jobs: int
    reprocessing_worker_poll_interval_seconds: int
    reprocessing_worker_batch_size: int
    valuation_scheduler_poll_interval_seconds: int
    valuation_scheduler_batch_size: int
    valuation_scheduler_dispatch_rounds: int
    dlq_budget_events_per_window: int
    operating_band_policy: OperatingBandPolicy
    calculator_peak_lag_age_seconds: dict[str, int]
    replay_isolation_mode: str
    partition_growth_strategy: str
    replay_dry_run_supported: bool = True


def build_operating_policy_config(
    *,
    runtime_policy: IngestionRuntimePolicySettings,
    operating_band_policy: OperatingBandPolicy,
) -> IngestionOperatingPolicyConfig:
    return IngestionOperatingPolicyConfig(
        lookback_minutes_default=runtime_policy.default_lookback_minutes,
        failure_rate_threshold_default=runtime_policy.default_failure_rate_threshold,
        queue_latency_threshold_seconds_default=runtime_policy.default_queue_latency_threshold_seconds,
        backlog_age_threshold_seconds_default=runtime_policy.default_backlog_age_threshold_seconds,
        replay_max_records_per_request=runtime_policy.replay_max_records_per_request,
        replay_max_backlog_jobs=runtime_policy.replay_max_backlog_jobs,
        reprocessing_worker_poll_interval_seconds=(
            runtime_policy.reprocessing_worker_poll_interval_seconds
        ),
        reprocessing_worker_batch_size=runtime_policy.reprocessing_worker_batch_size,
        valuation_scheduler_poll_interval_seconds=(
            runtime_policy.valuation_scheduler_poll_interval_seconds
        ),
        valuation_scheduler_batch_size=runtime_policy.valuation_scheduler_batch_size,
        valuation_scheduler_dispatch_rounds=runtime_policy.valuation_scheduler_dispatch_rounds,
        dlq_budget_events_per_window=runtime_policy.dlq_budget_events_per_window,
        operating_band_policy=operating_band_policy,
        calculator_peak_lag_age_seconds=dict(runtime_policy.calculator_peak_lag_age_seconds),
        replay_isolation_mode=runtime_policy.replay_isolation_mode,
        partition_growth_strategy=runtime_policy.partition_growth_strategy,
    )


def _replay_isolation_mode(value: str) -> Literal["shared_workers", "dedicated_workers"]:
    if value in {"shared_workers", "dedicated_workers"}:
        return value  # type: ignore[return-value]
    return "shared_workers"


def _partition_growth_strategy(
    value: str,
) -> Literal["scale_out_only", "pre_shard_large_portfolios"]:
    if value in {"scale_out_only", "pre_shard_large_portfolios"}:
        return value  # type: ignore[return-value]
    return "scale_out_only"


def _positive_int(value: int) -> int:
    return max(1, int(value))


def build_operating_policy_response(
    config: IngestionOperatingPolicyConfig,
) -> IngestionOpsPolicyResponse:
    replay_isolation_mode = _replay_isolation_mode(config.replay_isolation_mode)
    partition_growth_strategy = _partition_growth_strategy(config.partition_growth_strategy)
    calculator_peak_lag_age_seconds = {
        key: _positive_int(value) for key, value in config.calculator_peak_lag_age_seconds.items()
    }
    operating_band_policy = config.operating_band_policy
    values = {
        "lookback_minutes_default": config.lookback_minutes_default,
        "failure_rate_threshold_default": str(config.failure_rate_threshold_default),
        "queue_latency_threshold_seconds_default": config.queue_latency_threshold_seconds_default,
        "backlog_age_threshold_seconds_default": config.backlog_age_threshold_seconds_default,
        "replay_max_records_per_request": _positive_int(config.replay_max_records_per_request),
        "replay_max_backlog_jobs": _positive_int(config.replay_max_backlog_jobs),
        "reprocessing_worker_poll_interval_seconds": _positive_int(
            config.reprocessing_worker_poll_interval_seconds
        ),
        "reprocessing_worker_batch_size": _positive_int(config.reprocessing_worker_batch_size),
        "valuation_scheduler_poll_interval_seconds": _positive_int(
            config.valuation_scheduler_poll_interval_seconds
        ),
        "valuation_scheduler_batch_size": _positive_int(config.valuation_scheduler_batch_size),
        "valuation_scheduler_dispatch_rounds": _positive_int(
            config.valuation_scheduler_dispatch_rounds
        ),
        "dlq_budget_events_per_window": _positive_int(config.dlq_budget_events_per_window),
        "operating_band_yellow_backlog_age_seconds": (
            operating_band_policy.yellow_backlog_age_seconds
        ),
        "operating_band_orange_backlog_age_seconds": (
            operating_band_policy.orange_backlog_age_seconds
        ),
        "operating_band_red_backlog_age_seconds": operating_band_policy.red_backlog_age_seconds,
        "operating_band_yellow_dlq_pressure_ratio": str(
            operating_band_policy.yellow_dlq_pressure_ratio
        ),
        "operating_band_orange_dlq_pressure_ratio": str(
            operating_band_policy.orange_dlq_pressure_ratio
        ),
        "operating_band_red_dlq_pressure_ratio": str(operating_band_policy.red_dlq_pressure_ratio),
        "calculator_peak_lag_age_seconds": calculator_peak_lag_age_seconds,
        "replay_isolation_mode": replay_isolation_mode,
        "partition_growth_strategy": partition_growth_strategy,
        "replay_dry_run_supported": config.replay_dry_run_supported,
    }
    serialized = json.dumps(values, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return IngestionOpsPolicyResponse(
        policy_version="v1",
        policy_fingerprint=fingerprint,
        lookback_minutes_default=config.lookback_minutes_default,
        failure_rate_threshold_default=config.failure_rate_threshold_default,
        queue_latency_threshold_seconds_default=config.queue_latency_threshold_seconds_default,
        backlog_age_threshold_seconds_default=config.backlog_age_threshold_seconds_default,
        replay_max_records_per_request=_positive_int(config.replay_max_records_per_request),
        replay_max_backlog_jobs=_positive_int(config.replay_max_backlog_jobs),
        reprocessing_worker_poll_interval_seconds=_positive_int(
            config.reprocessing_worker_poll_interval_seconds
        ),
        reprocessing_worker_batch_size=_positive_int(config.reprocessing_worker_batch_size),
        valuation_scheduler_poll_interval_seconds=_positive_int(
            config.valuation_scheduler_poll_interval_seconds
        ),
        valuation_scheduler_batch_size=_positive_int(config.valuation_scheduler_batch_size),
        valuation_scheduler_dispatch_rounds=_positive_int(
            config.valuation_scheduler_dispatch_rounds
        ),
        dlq_budget_events_per_window=_positive_int(config.dlq_budget_events_per_window),
        operating_band_yellow_backlog_age_seconds=(
            operating_band_policy.yellow_backlog_age_seconds
        ),
        operating_band_orange_backlog_age_seconds=(
            operating_band_policy.orange_backlog_age_seconds
        ),
        operating_band_red_backlog_age_seconds=operating_band_policy.red_backlog_age_seconds,
        operating_band_yellow_dlq_pressure_ratio=operating_band_policy.yellow_dlq_pressure_ratio,
        operating_band_orange_dlq_pressure_ratio=operating_band_policy.orange_dlq_pressure_ratio,
        operating_band_red_dlq_pressure_ratio=operating_band_policy.red_dlq_pressure_ratio,
        calculator_peak_lag_age_seconds=calculator_peak_lag_age_seconds,
        replay_isolation_mode=replay_isolation_mode,
        partition_growth_strategy=partition_growth_strategy,
        replay_dry_run_supported=config.replay_dry_run_supported,
    )
