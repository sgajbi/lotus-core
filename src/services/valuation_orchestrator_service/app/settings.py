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
class ValuationRuntimeSettings:
    valuation_scheduler_poll_interval_seconds: int
    valuation_scheduler_batch_size: int
    valuation_scheduler_dispatch_rounds: int
    reprocessing_worker_poll_interval_seconds: int
    reprocessing_worker_batch_size: int
    reprocessing_worker_max_attempts: int


def load_valuation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 30,
    scheduler_batch_size_default: int = 100,
    scheduler_dispatch_rounds_default: int = 3,
    worker_poll_interval_default: int = 10,
    worker_batch_size_default: int = 10,
) -> ValuationRuntimeSettings:
    return ValuationRuntimeSettings(
        valuation_scheduler_poll_interval_seconds=_env_positive_int(
            "VALUATION_SCHEDULER_POLL_INTERVAL", scheduler_poll_interval_default
        ),
        valuation_scheduler_batch_size=_env_positive_int(
            "VALUATION_SCHEDULER_BATCH_SIZE", scheduler_batch_size_default
        ),
        valuation_scheduler_dispatch_rounds=_env_positive_int(
            "VALUATION_SCHEDULER_DISPATCH_ROUNDS", scheduler_dispatch_rounds_default
        ),
        reprocessing_worker_poll_interval_seconds=_env_positive_int(
            "REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", worker_poll_interval_default
        ),
        reprocessing_worker_batch_size=_env_positive_int(
            "REPROCESSING_WORKER_BATCH_SIZE", worker_batch_size_default
        ),
        reprocessing_worker_max_attempts=_env_positive_int("REPROCESSING_WORKER_MAX_ATTEMPTS", 3),
    )


def get_valuation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 30,
    scheduler_batch_size_default: int = 100,
    scheduler_dispatch_rounds_default: int = 3,
    worker_poll_interval_default: int = 10,
    worker_batch_size_default: int = 10,
) -> ValuationRuntimeSettings:
    return load_valuation_runtime_settings(
        scheduler_poll_interval_default=scheduler_poll_interval_default,
        scheduler_batch_size_default=scheduler_batch_size_default,
        scheduler_dispatch_rounds_default=scheduler_dispatch_rounds_default,
        worker_poll_interval_default=worker_poll_interval_default,
        worker_batch_size_default=worker_batch_size_default,
    )
