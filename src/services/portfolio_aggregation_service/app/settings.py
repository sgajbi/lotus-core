from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.runtime_settings import env_int

SERVICE_NAME = "portfolio aggregation service"


def _env_positive_int(name: str, default: int) -> int:
    return int(
        env_int(
            name,
            max(1, int(default)),
            service_name=SERVICE_NAME,
            minimum=1,
            minimum_fallback=1,
        )
    )


@dataclass(frozen=True, slots=True)
class AggregationRuntimeSettings:
    portfolio_aggregation_worker_count: int
    aggregation_scheduler_poll_interval_seconds: int
    aggregation_scheduler_batch_size: int
    aggregation_job_lease_duration_seconds: int
    aggregation_scheduler_max_attempts: int


def get_aggregation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 5,
    scheduler_batch_size_default: int = 100,
) -> AggregationRuntimeSettings:
    return AggregationRuntimeSettings(
        portfolio_aggregation_worker_count=_env_positive_int(
            "PORTFOLIO_AGGREGATION_WORKER_COUNT",
            4,
        ),
        aggregation_scheduler_poll_interval_seconds=_env_positive_int(
            "AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS",
            scheduler_poll_interval_default,
        ),
        aggregation_scheduler_batch_size=_env_positive_int(
            "AGGREGATION_SCHEDULER_BATCH_SIZE",
            scheduler_batch_size_default,
        ),
        aggregation_job_lease_duration_seconds=_env_positive_int(
            "AGGREGATION_JOB_LEASE_DURATION_SECONDS",
            900,
        ),
        aggregation_scheduler_max_attempts=_env_positive_int(
            "AGGREGATION_SCHEDULER_MAX_ATTEMPTS",
            3,
        ),
    )
