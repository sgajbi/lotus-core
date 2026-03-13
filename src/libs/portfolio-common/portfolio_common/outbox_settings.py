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
class OutboxRuntimeSettings:
    poll_interval_seconds: int
    batch_size: int
    max_retries: int


def get_outbox_runtime_settings(
    *,
    poll_interval_default: int = 5,
    batch_size_default: int = 50,
    max_retries_default: int = 3,
) -> OutboxRuntimeSettings:
    return OutboxRuntimeSettings(
        poll_interval_seconds=_env_positive_int(
            "OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS",
            poll_interval_default,
        ),
        batch_size=_env_positive_int(
            "OUTBOX_DISPATCHER_BATCH_SIZE",
            batch_size_default,
        ),
        max_retries=_env_positive_int("OUTBOX_DISPATCHER_MAX_RETRIES", max_retries_default),
    )
