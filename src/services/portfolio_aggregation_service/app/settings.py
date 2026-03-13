from __future__ import annotations

import os
from dataclasses import dataclass


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return max(1, int(default))
    try:
        return max(1, int(raw))
    except Exception:
        return max(1, int(default))


@dataclass(frozen=True, slots=True)
class AggregationRuntimeSettings:
    aggregation_scheduler_poll_interval_seconds: int
    aggregation_scheduler_batch_size: int
    aggregation_scheduler_max_attempts: int


def get_aggregation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 5,
    scheduler_batch_size_default: int = 100,
) -> AggregationRuntimeSettings:
    return AggregationRuntimeSettings(
        aggregation_scheduler_poll_interval_seconds=_env_positive_int(
            "AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS",
            scheduler_poll_interval_default,
        ),
        aggregation_scheduler_batch_size=_env_positive_int(
            "AGGREGATION_SCHEDULER_BATCH_SIZE",
            scheduler_batch_size_default,
        ),
        aggregation_scheduler_max_attempts=_env_positive_int(
            "AGGREGATION_SCHEDULER_MAX_ATTEMPTS",
            3,
        ),
    )
