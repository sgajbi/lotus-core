from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

def _normalize_positive_default(default: int) -> int:
    try:
        return max(1, int(default))
    except Exception:
        return 1


def _env_positive_int(name: str, default: int) -> int:
    safe_default = _normalize_positive_default(default)
    raw = os.getenv(name)
    if raw is None:
        return safe_default
    try:
        value = int(raw)
    except Exception:
        logger.warning(
            "Invalid outbox runtime setting; falling back to default.",
            extra={"setting": name, "raw_value": raw, "default": safe_default},
        )
        return safe_default
    if value <= 0:
        logger.warning(
            "Non-positive outbox runtime setting; falling back to default.",
            extra={"setting": name, "raw_value": raw, "default": safe_default},
        )
        return safe_default
    return value


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
