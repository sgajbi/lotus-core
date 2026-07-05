from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.runtime_settings import RuntimeConfigurationError
from portfolio_common.runtime_settings import env_int as shared_env_int

VALUATION_RUNTIME_SERVICE_NAME = "valuation runtime"


def _env_positive_int(name: str, default: int) -> int:
    safe_default = max(1, int(default))
    return shared_env_int(
        name,
        safe_default,
        service_name=VALUATION_RUNTIME_SERVICE_NAME,
        minimum=1,
        minimum_fallback=1,
    )


@dataclass(frozen=True, slots=True)
class ValuationRuntimeSettings:
    valuation_scheduler_poll_interval_seconds: int
    valuation_scheduler_batch_size: int
    valuation_scheduler_dispatch_rounds: int
    valuation_scheduler_poll_budget_seconds: int
    valuation_scheduler_dispatch_budget_seconds: int
    valuation_scheduler_stale_timeout_minutes: int
    valuation_scheduler_max_attempts: int
    reprocessing_worker_poll_interval_seconds: int
    reprocessing_worker_batch_size: int
    reprocessing_worker_stale_timeout_minutes: int
    reprocessing_worker_max_attempts: int


ValuationRuntimeConfigurationError = RuntimeConfigurationError


def load_valuation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 30,
    scheduler_batch_size_default: int = 100,
    scheduler_dispatch_rounds_default: int = 10,
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
        valuation_scheduler_poll_budget_seconds=_env_positive_int(
            "VALUATION_SCHEDULER_POLL_BUDGET_SECONDS", scheduler_poll_interval_default
        ),
        valuation_scheduler_dispatch_budget_seconds=_env_positive_int(
            "VALUATION_SCHEDULER_DISPATCH_BUDGET_SECONDS", 10
        ),
        valuation_scheduler_stale_timeout_minutes=_env_positive_int(
            "VALUATION_SCHEDULER_STALE_TIMEOUT_MINUTES", 15
        ),
        valuation_scheduler_max_attempts=_env_positive_int("VALUATION_SCHEDULER_MAX_ATTEMPTS", 3),
        reprocessing_worker_poll_interval_seconds=_env_positive_int(
            "REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", worker_poll_interval_default
        ),
        reprocessing_worker_batch_size=_env_positive_int(
            "REPROCESSING_WORKER_BATCH_SIZE", worker_batch_size_default
        ),
        reprocessing_worker_stale_timeout_minutes=_env_positive_int(
            "REPROCESSING_WORKER_STALE_TIMEOUT_MINUTES", 15
        ),
        reprocessing_worker_max_attempts=_env_positive_int("REPROCESSING_WORKER_MAX_ATTEMPTS", 3),
    )


def get_valuation_runtime_settings(
    *,
    scheduler_poll_interval_default: int = 30,
    scheduler_batch_size_default: int = 100,
    scheduler_dispatch_rounds_default: int = 10,
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
