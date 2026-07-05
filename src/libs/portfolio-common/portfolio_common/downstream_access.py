from __future__ import annotations

from dataclasses import dataclass

from .runtime_settings import env_bool, env_int

DOWNSTREAM_ACCESS_SERVICE_NAME = "portfolio common downstream access"


@dataclass(frozen=True, slots=True)
class DownstreamAccessPolicy:
    connect_timeout_seconds: float
    request_timeout_seconds: float
    retry_max_attempts: int
    retry_backoff_seconds: float
    retry_max_elapsed_seconds: float
    circuit_breaker_enabled: bool
    max_page_size: int
    max_batch_size: int
    cache_allowed: bool


def load_downstream_access_policy() -> DownstreamAccessPolicy:
    return DownstreamAccessPolicy(
        connect_timeout_seconds=_env_milliseconds(
            "LOTUS_CORE_DOWNSTREAM_CONNECT_TIMEOUT_MS",
            500,
            minimum=1,
        ),
        request_timeout_seconds=_env_milliseconds(
            "LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS",
            5_000,
            minimum=1,
        ),
        retry_max_attempts=env_int(
            "LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ATTEMPTS",
            15,
            service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
            minimum=1,
        ),
        retry_backoff_seconds=_env_milliseconds(
            "LOTUS_CORE_DOWNSTREAM_RETRY_BACKOFF_MS",
            4_000,
            minimum=0,
        ),
        retry_max_elapsed_seconds=_env_milliseconds(
            "LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ELAPSED_MS",
            60_000,
            minimum=1,
        ),
        circuit_breaker_enabled=env_bool(
            "LOTUS_CORE_DOWNSTREAM_CIRCUIT_BREAKER_ENABLED",
            False,
            service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
        ),
        max_page_size=env_int(
            "LOTUS_CORE_DOWNSTREAM_MAX_PAGE_SIZE",
            500,
            service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
            minimum=1,
        ),
        max_batch_size=env_int(
            "LOTUS_CORE_DOWNSTREAM_MAX_BATCH_SIZE",
            500,
            service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
            minimum=1,
        ),
        cache_allowed=env_bool(
            "LOTUS_CORE_DOWNSTREAM_CACHE_ALLOWED",
            True,
            service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
        ),
    )


def _env_milliseconds(name: str, default: int, *, minimum: int) -> float:
    milliseconds = env_int(
        name,
        default,
        service_name=DOWNSTREAM_ACCESS_SERVICE_NAME,
        minimum=minimum,
    )
    return milliseconds / 1000
