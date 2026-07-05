from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from portfolio_common.runtime_settings import (
    RuntimeConfigurationError,
    env_int,
    env_json_map,
    env_str,
)

SERVICE_NAME = "portfolio common Kafka producer"
DEFAULT_PRODUCER_SERVICE = "portfolio_common"
DEFAULT_CLIENT_ID = "portfolio-analytics-producer"
DEFAULT_RETRIES = 5
DEFAULT_LINGER_MS = 5
DEFAULT_BATCH_NUM_MESSAGES = 1000
DEFAULT_COMPRESSION_TYPE = "zstd"
DEFAULT_DELIVERY_TIMEOUT_MS = 120000
DEFAULT_REQUEST_TIMEOUT_MS = 30000
DEFAULT_QUEUE_BUFFERING_MAX_MESSAGES = 100000
DEFAULT_QUEUE_BUFFERING_MAX_KBYTES = 1048576

DEFAULTS_JSON_ENV = "LOTUS_CORE_KAFKA_PRODUCER_DEFAULTS_JSON"
SERVICE_OVERRIDES_JSON_ENV = "LOTUS_CORE_KAFKA_PRODUCER_SERVICE_OVERRIDES_JSON"

_SUPPORTED_CONFIG_KEYS = {
    "client.id",
    "retries",
    "linger.ms",
    "batch.num.messages",
    "compression.type",
    "delivery.timeout.ms",
    "request.timeout.ms",
    "queue.buffering.max.messages",
    "queue.buffering.max.kbytes",
}
_INT_CONFIG_KEYS = {
    "retries",
    "linger.ms",
    "batch.num.messages",
    "delivery.timeout.ms",
    "request.timeout.ms",
    "queue.buffering.max.messages",
    "queue.buffering.max.kbytes",
}
_NON_NEGATIVE_INT_KEYS = {"retries", "linger.ms"}
_POSITIVE_INT_KEYS = _INT_CONFIG_KEYS - _NON_NEGATIVE_INT_KEYS
_ALLOWED_COMPRESSION_TYPES = {"none", "gzip", "snappy", "lz4", "zstd"}


@dataclass(frozen=True)
class KafkaProducerPolicy:
    service_name: str
    client_id: str
    retries: int
    linger_ms: int
    batch_num_messages: int
    compression_type: str
    delivery_timeout_ms: int
    request_timeout_ms: int
    queue_buffering_max_messages: int
    queue_buffering_max_kbytes: int

    def as_confluent_config(self) -> dict[str, Any]:
        return {
            "client.id": self.client_id,
            "retries": self.retries,
            "linger.ms": self.linger_ms,
            "batch.num.messages": self.batch_num_messages,
            "compression.type": self.compression_type,
            "delivery.timeout.ms": self.delivery_timeout_ms,
            "request.timeout.ms": self.request_timeout_ms,
            "queue.buffering.max.messages": self.queue_buffering_max_messages,
            "queue.buffering.max.kbytes": self.queue_buffering_max_kbytes,
        }


def load_kafka_producer_policy(
    *,
    service_name: str = DEFAULT_PRODUCER_SERVICE,
) -> KafkaProducerPolicy:
    normalized_service = _normalize_service_name(service_name)
    merged = _base_policy_values(normalized_service)
    merged.update(_load_defaults_json())
    merged.update(_load_service_override_json(normalized_service))
    return _build_policy(normalized_service, merged)


def _normalize_service_name(service_name: str) -> str:
    normalized = str(service_name or "").strip()
    if not normalized:
        raise RuntimeConfigurationError(
            "Invalid Kafka producer configuration for service_name: expected non-empty value"
        )
    return normalized


def _base_policy_values(service_name: str) -> dict[str, Any]:
    return {
        "client.id": env_str("LOTUS_CORE_KAFKA_PRODUCER_CLIENT_ID", DEFAULT_CLIENT_ID),
        "retries": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_RETRIES",
            DEFAULT_RETRIES,
            service_name=SERVICE_NAME,
            minimum=0,
        ),
        "linger.ms": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_LINGER_MS",
            DEFAULT_LINGER_MS,
            service_name=SERVICE_NAME,
            minimum=0,
        ),
        "batch.num.messages": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_BATCH_NUM_MESSAGES",
            DEFAULT_BATCH_NUM_MESSAGES,
            service_name=SERVICE_NAME,
            minimum=1,
        ),
        "compression.type": env_str(
            "LOTUS_CORE_KAFKA_PRODUCER_COMPRESSION_TYPE", DEFAULT_COMPRESSION_TYPE
        ),
        "delivery.timeout.ms": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS",
            DEFAULT_DELIVERY_TIMEOUT_MS,
            service_name=SERVICE_NAME,
            minimum=1,
        ),
        "request.timeout.ms": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_REQUEST_TIMEOUT_MS",
            DEFAULT_REQUEST_TIMEOUT_MS,
            service_name=SERVICE_NAME,
            minimum=1,
        ),
        "queue.buffering.max.messages": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_MESSAGES",
            DEFAULT_QUEUE_BUFFERING_MAX_MESSAGES,
            service_name=SERVICE_NAME,
            minimum=1,
        ),
        "queue.buffering.max.kbytes": env_int(
            "LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_KBYTES",
            DEFAULT_QUEUE_BUFFERING_MAX_KBYTES,
            service_name=SERVICE_NAME,
            minimum=1,
        ),
    } | _service_identity_default(service_name)


def _service_identity_default(service_name: str) -> dict[str, str]:
    configured = os.getenv("LOTUS_CORE_KAFKA_PRODUCER_CLIENT_ID")
    if configured is not None and configured.strip():
        return {}
    if service_name == DEFAULT_PRODUCER_SERVICE:
        return {}
    return {"client.id": f"{service_name}-producer"}


def _load_defaults_json() -> dict[str, Any]:
    raw = os.getenv(DEFAULTS_JSON_ENV, "").strip()
    if not raw:
        return {}
    return _sanitize_config_map(
        env_json_map(DEFAULTS_JSON_ENV, service_name=SERVICE_NAME),
        context=DEFAULTS_JSON_ENV,
    )


def _load_service_override_json(service_name: str) -> dict[str, Any]:
    raw = os.getenv(SERVICE_OVERRIDES_JSON_ENV, "").strip()
    if not raw:
        return {}
    overrides = env_json_map(SERVICE_OVERRIDES_JSON_ENV, service_name=SERVICE_NAME)
    service_config = overrides.get(service_name)
    if service_config is None:
        return {}
    if not isinstance(service_config, dict):
        raise RuntimeConfigurationError(
            "Invalid Kafka producer configuration for "
            f"{SERVICE_OVERRIDES_JSON_ENV}[{service_name}]: expected JSON object"
        )
    return _sanitize_config_map(
        service_config,
        context=f"{SERVICE_OVERRIDES_JSON_ENV}[{service_name}]",
    )


def _sanitize_config_map(raw: dict[str, Any], *, context: str) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _SUPPORTED_CONFIG_KEYS:
            raise RuntimeConfigurationError(
                f"Invalid Kafka producer configuration for {context}: unsupported key {key!r}"
            )
        sanitized[key] = _coerce_config_value(key, value, context=context)
    return sanitized


def _coerce_config_value(key: str, value: Any, *, context: str) -> Any:
    if key in _INT_CONFIG_KEYS:
        return _coerce_int_config_value(key, value, context=context)
    if key == "compression.type":
        return _coerce_compression_type(value, context=context)
    if key == "client.id":
        return _coerce_non_empty_string(key, value, context=context)
    return value


def _coerce_int_config_value(key: str, value: Any, *, context: str) -> int:
    if isinstance(value, bool):
        raise RuntimeConfigurationError(
            f"Invalid Kafka producer configuration for {context}.{key}: expected integer"
        )
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigurationError(
            f"Invalid Kafka producer configuration for {context}.{key}: expected integer"
        ) from exc
    if key in _POSITIVE_INT_KEYS and coerced < 1:
        raise RuntimeConfigurationError(
            f"Invalid Kafka producer configuration for {context}.{key}: expected value >= 1"
        )
    if key in _NON_NEGATIVE_INT_KEYS and coerced < 0:
        raise RuntimeConfigurationError(
            f"Invalid Kafka producer configuration for {context}.{key}: expected value >= 0"
        )
    return coerced


def _coerce_compression_type(value: Any, *, context: str) -> str:
    normalized = _coerce_non_empty_string("compression.type", value, context=context).lower()
    if normalized not in _ALLOWED_COMPRESSION_TYPES:
        raise RuntimeConfigurationError(
            "Invalid Kafka producer configuration for "
            f"{context}.compression.type: expected one of {sorted(_ALLOWED_COMPRESSION_TYPES)}"
        )
    return normalized


def _coerce_non_empty_string(key: str, value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeConfigurationError(
            f"Invalid Kafka producer configuration for {context}.{key}: expected non-empty string"
        )
    return value.strip()


def _build_policy(service_name: str, values: dict[str, Any]) -> KafkaProducerPolicy:
    policy = KafkaProducerPolicy(
        service_name=service_name,
        client_id=_coerce_non_empty_string("client.id", values["client.id"], context=service_name),
        retries=_coerce_int_config_value("retries", values["retries"], context=service_name),
        linger_ms=_coerce_int_config_value("linger.ms", values["linger.ms"], context=service_name),
        batch_num_messages=_coerce_int_config_value(
            "batch.num.messages", values["batch.num.messages"], context=service_name
        ),
        compression_type=_coerce_compression_type(values["compression.type"], context=service_name),
        delivery_timeout_ms=_coerce_int_config_value(
            "delivery.timeout.ms", values["delivery.timeout.ms"], context=service_name
        ),
        request_timeout_ms=_coerce_int_config_value(
            "request.timeout.ms", values["request.timeout.ms"], context=service_name
        ),
        queue_buffering_max_messages=_coerce_int_config_value(
            "queue.buffering.max.messages",
            values["queue.buffering.max.messages"],
            context=service_name,
        ),
        queue_buffering_max_kbytes=_coerce_int_config_value(
            "queue.buffering.max.kbytes",
            values["queue.buffering.max.kbytes"],
            context=service_name,
        ),
    )
    _validate_policy_relationships(policy)
    return policy


def _validate_policy_relationships(policy: KafkaProducerPolicy) -> None:
    if policy.delivery_timeout_ms <= policy.request_timeout_ms:
        raise RuntimeConfigurationError(
            "Invalid Kafka producer configuration for delivery.timeout.ms: "
            "expected greater than request.timeout.ms"
        )
    if policy.delivery_timeout_ms <= policy.linger_ms:
        raise RuntimeConfigurationError(
            "Invalid Kafka producer configuration for delivery.timeout.ms: "
            "expected greater than linger.ms"
        )
