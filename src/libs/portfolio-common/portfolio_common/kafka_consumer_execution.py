from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from portfolio_common.runtime_settings import env_json_map, invalid_env_setting

CONFIG_SERVICE_NAME = "portfolio common kafka consumer execution"
DEFAULTS_ENV = "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON"
GROUP_OVERRIDES_ENV = "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON"
ORDERING_PARTITION = "partition"
OVERLOAD_PAUSE_POLL = "pause_poll"
SUPPORTED_ORDERING_KEYS = {ORDERING_PARTITION}
SUPPORTED_OVERLOAD_BEHAVIORS = {OVERLOAD_PAUSE_POLL}


@dataclass(frozen=True)
class KafkaConsumerExecutionProfile:
    poll_timeout_seconds: float = 1.0
    max_in_flight_messages: int = 1
    ordering_key: str = ORDERING_PARTITION
    per_key_concurrency: int = 1
    shutdown_drain_timeout_seconds: float = 30.0
    overload_behavior: str = OVERLOAD_PAUSE_POLL

    def __post_init__(self) -> None:
        _require_positive_float("poll_timeout_seconds", self.poll_timeout_seconds)
        _require_positive_int("max_in_flight_messages", self.max_in_flight_messages)
        _require_supported_value("ordering_key", self.ordering_key, SUPPORTED_ORDERING_KEYS)
        _require_positive_int("per_key_concurrency", self.per_key_concurrency)
        _require_positive_float(
            "shutdown_drain_timeout_seconds",
            self.shutdown_drain_timeout_seconds,
        )
        _require_supported_value(
            "overload_behavior",
            self.overload_behavior,
            SUPPORTED_OVERLOAD_BEHAVIORS,
        )
        if self.per_key_concurrency != 1:
            raise ValueError("per_key_concurrency must be 1 to preserve ordered offset commits.")

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> KafkaConsumerExecutionProfile:
        defaults = cls()
        allowed = set(defaults.to_mapping())
        unknown_keys = sorted(set(raw) - allowed)
        if unknown_keys:
            raise ValueError(f"unsupported execution profile keys: {unknown_keys}")
        return cls(
            poll_timeout_seconds=_coerce_float(
                raw.get("poll_timeout_seconds", defaults.poll_timeout_seconds),
                "poll_timeout_seconds",
            ),
            max_in_flight_messages=_coerce_int(
                raw.get("max_in_flight_messages", defaults.max_in_flight_messages),
                "max_in_flight_messages",
            ),
            ordering_key=_coerce_str(
                raw.get("ordering_key", defaults.ordering_key),
                "ordering_key",
            ),
            per_key_concurrency=_coerce_int(
                raw.get("per_key_concurrency", defaults.per_key_concurrency),
                "per_key_concurrency",
            ),
            shutdown_drain_timeout_seconds=_coerce_float(
                raw.get(
                    "shutdown_drain_timeout_seconds",
                    defaults.shutdown_drain_timeout_seconds,
                ),
                "shutdown_drain_timeout_seconds",
            ),
            overload_behavior=_coerce_str(
                raw.get("overload_behavior", defaults.overload_behavior),
                "overload_behavior",
            ),
        )

    def merge(self, override: dict[str, object]) -> KafkaConsumerExecutionProfile:
        return self.from_mapping({**self.to_mapping(), **override})

    def to_mapping(self) -> dict[str, object]:
        return {
            "poll_timeout_seconds": self.poll_timeout_seconds,
            "max_in_flight_messages": self.max_in_flight_messages,
            "ordering_key": self.ordering_key,
            "per_key_concurrency": self.per_key_concurrency,
            "shutdown_drain_timeout_seconds": self.shutdown_drain_timeout_seconds,
            "overload_behavior": self.overload_behavior,
        }


def load_kafka_consumer_execution_profile(group_id: str) -> KafkaConsumerExecutionProfile:
    profile = _load_default_execution_profile()
    group_override = _load_group_execution_override(group_id)
    if not group_override:
        return profile
    try:
        return profile.merge(group_override)
    except ValueError as exc:
        return _invalid_profile(GROUP_OVERRIDES_ENV, group_override, reason=str(exc))


def _load_default_execution_profile() -> KafkaConsumerExecutionProfile:
    raw = env_json_map(DEFAULTS_ENV, service_name=CONFIG_SERVICE_NAME)
    if not raw:
        return KafkaConsumerExecutionProfile()
    try:
        return KafkaConsumerExecutionProfile.from_mapping(raw)
    except ValueError as exc:
        return _invalid_profile(DEFAULTS_ENV, raw, reason=str(exc))


def _load_group_execution_override(group_id: str) -> dict[str, object]:
    raw = env_json_map(GROUP_OVERRIDES_ENV, service_name=CONFIG_SERVICE_NAME)
    if not raw:
        return {}
    group_profile = raw.get(group_id)
    if group_profile is None:
        return {}
    if not isinstance(group_profile, dict):
        invalid_env_setting(
            name=GROUP_OVERRIDES_ENV,
            raw=group_profile,
            default={},
            reason=f"profile for group '{group_id}' must be a JSON object",
            service_name=CONFIG_SERVICE_NAME,
        )
        return {}
    return group_profile


def _invalid_profile(
    name: str,
    raw: object,
    *,
    reason: str,
) -> KafkaConsumerExecutionProfile:
    invalid_env_setting(
        name=name,
        raw=raw,
        default=KafkaConsumerExecutionProfile().to_mapping(),
        reason=reason,
        service_name=CONFIG_SERVICE_NAME,
    )
    return KafkaConsumerExecutionProfile()


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _coerce_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _require_positive_float(field_name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")


def _require_positive_int(field_name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")


def _require_supported_value(
    field_name: str,
    value: str,
    supported_values: set[str],
) -> None:
    if value not in supported_values:
        raise ValueError(f"{field_name} must be one of {sorted(supported_values)}")
