from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

STRICT_CONFIG_VALIDATION_ENV = "LOTUS_CORE_STRICT_CONFIG_VALIDATION"
LOCAL_CONFIG_ENVIRONMENTS = {"", "local", "dev", "development", "test"}
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
FALSY_ENV_VALUES = {"0", "false", "no", "off"}


class RuntimeConfigurationError(ValueError):
    """Raised when strict runtime configuration validation rejects an env value."""


def strict_config_validation_enabled() -> bool:
    raw = os.getenv(STRICT_CONFIG_VALIDATION_ENV)
    if raw is not None:
        return raw.strip().lower() in TRUTHY_ENV_VALUES
    environment = os.getenv("ENVIRONMENT", "local").strip().lower()
    return environment not in LOCAL_CONFIG_ENVIRONMENTS


def env_bool(name: str, default: bool, *, service_name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in TRUTHY_ENV_VALUES:
        return True
    if normalized in FALSY_ENV_VALUES:
        return False
    return bool(
        invalid_env_setting(
            name=name,
            raw=raw,
            default=default,
            reason="expected boolean value",
            service_name=service_name,
        )
    )


def env_int(
    name: str,
    default: int,
    *,
    service_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
    minimum_fallback: int | None = None,
) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(
            invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason="expected integer value",
                service_name=service_name,
            )
        )
    if minimum is not None and value < minimum:
        return int(
            invalid_env_setting(
                name=name,
                raw=raw,
                default=default if minimum_fallback is None else minimum_fallback,
                reason=f"expected value >= {minimum}",
                service_name=service_name,
            )
        )
    if maximum is not None and value > maximum:
        return int(
            invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason=f"expected value <= {maximum}",
                service_name=service_name,
            )
        )
    return value


def env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw


def env_json_map(name: str, *, service_name: str) -> dict[str, Any]:
    raw = env_str(name, "{}")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        invalid_env_setting(
            name=name,
            raw=raw,
            default={},
            reason="expected JSON object",
            service_name=service_name,
        )
        return {}
    if not isinstance(decoded, dict):
        invalid_env_setting(
            name=name,
            raw=raw,
            default={},
            reason="expected JSON object",
            service_name=service_name,
        )
        return {}
    return decoded


def invalid_env_setting(
    *,
    name: str,
    raw: object,
    default: object,
    reason: str,
    service_name: str,
) -> object:
    if strict_config_validation_enabled():
        raise RuntimeConfigurationError(
            f"Invalid {service_name} configuration for {name}: {reason}"
        )
    logger.warning(
        "Invalid runtime setting; falling back to default.",
        extra={
            "setting": name,
            "raw_value": str(raw),
            "default": str(default),
            "reason": reason,
            "service": service_name,
        },
    )
    return default
