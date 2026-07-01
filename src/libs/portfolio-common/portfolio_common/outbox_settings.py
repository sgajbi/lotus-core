from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.runtime_settings import RuntimeConfigurationError
from portfolio_common.runtime_settings import env_int as shared_env_int

OUTBOX_RUNTIME_SERVICE_NAME = "outbox runtime"


def _normalize_positive_default(default: int) -> int:
    try:
        return max(1, int(default))
    except Exception:
        return 1


def _normalize_non_negative_default(default: int) -> int:
    try:
        return max(0, int(default))
    except Exception:
        return 0


def _env_positive_int(name: str, default: int) -> int:
    safe_default = _normalize_positive_default(default)
    return int(
        shared_env_int(
            name,
            safe_default,
            service_name=OUTBOX_RUNTIME_SERVICE_NAME,
            minimum=1,
        )
    )


def _env_non_negative_int(name: str, default: int) -> int:
    safe_default = _normalize_non_negative_default(default)
    return int(
        shared_env_int(
            name,
            safe_default,
            service_name=OUTBOX_RUNTIME_SERVICE_NAME,
            minimum=0,
        )
    )


@dataclass(frozen=True, slots=True)
class OutboxRuntimeSettings:
    poll_interval_seconds: int
    batch_size: int
    claim_lease_seconds: int
    max_retries: int
    retry_max_elapsed_seconds: int
    retry_initial_delay_seconds: int
    retry_max_delay_seconds: int
    retry_jitter_seconds: int


OutboxRuntimeConfigurationError = RuntimeConfigurationError


def get_outbox_runtime_settings(
    *,
    poll_interval_default: int = 5,
    batch_size_default: int = 50,
    claim_lease_default: int = 60,
    max_retries_default: int = 3,
    retry_max_elapsed_default: int = 0,
    retry_initial_delay_default: int = 5,
    retry_max_delay_default: int = 300,
    retry_jitter_default: int = 0,
) -> OutboxRuntimeSettings:
    retry_initial_delay_seconds = _env_positive_int(
        "OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS",
        retry_initial_delay_default,
    )
    retry_max_delay_seconds = max(
        retry_initial_delay_seconds,
        _env_positive_int(
            "OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS",
            retry_max_delay_default,
        ),
    )
    return OutboxRuntimeSettings(
        poll_interval_seconds=_env_positive_int(
            "OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS",
            poll_interval_default,
        ),
        batch_size=_env_positive_int(
            "OUTBOX_DISPATCHER_BATCH_SIZE",
            batch_size_default,
        ),
        claim_lease_seconds=_env_positive_int(
            "OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS",
            claim_lease_default,
        ),
        max_retries=_env_positive_int("OUTBOX_DISPATCHER_MAX_RETRIES", max_retries_default),
        retry_max_elapsed_seconds=_env_non_negative_int(
            "OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS",
            retry_max_elapsed_default,
        ),
        retry_initial_delay_seconds=retry_initial_delay_seconds,
        retry_max_delay_seconds=retry_max_delay_seconds,
        retry_jitter_seconds=_env_non_negative_int(
            "OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS",
            retry_jitter_default,
        ),
    )
