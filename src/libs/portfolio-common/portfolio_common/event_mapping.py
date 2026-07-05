"""Shared event mapping helpers for Kafka and outbox boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from confluent_kafka import Message
from pydantic import BaseModel

from .events import GOVERNED_EVENT_SCHEMA_VERSION

EventT = TypeVar("EventT", bound=BaseModel)
DEFAULT_ACCEPTED_EVENT_SCHEMA_VERSIONS = (GOVERNED_EVENT_SCHEMA_VERSION,)


class EventContractValidationError(ValueError):
    """Raised when transport event metadata violates a governed consumer contract."""


@dataclass(frozen=True)
class DecodedKafkaEventPayload:
    """Decoded Kafka payload plus deterministic transport identity."""

    event_id: str
    data: dict[str, Any]


def kafka_event_id(msg: Message) -> str:
    """Build the deterministic fallback identity for a Kafka message."""
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


def decode_kafka_event_payload(msg: Message) -> DecodedKafkaEventPayload:
    """Decode a Kafka message value as a JSON event payload."""
    return DecodedKafkaEventPayload(
        event_id=kafka_event_id(msg),
        data=json.loads(msg.value().decode("utf-8")),
    )


def validate_kafka_event_payload(
    payload: DecodedKafkaEventPayload,
    event_model: type[EventT],
    *,
    expected_event_type: str | None = None,
    accepted_schema_versions: tuple[str, ...] | None = None,
) -> EventT:
    """Validate a decoded Kafka payload against a governed event model."""
    accepted_versions = accepted_schema_versions
    if expected_event_type is not None and accepted_versions is None:
        accepted_versions = DEFAULT_ACCEPTED_EVENT_SCHEMA_VERSIONS
    if expected_event_type is not None:
        _require_expected_event_type(payload.data, expected_event_type)
    if accepted_versions is not None:
        _require_supported_schema_version(payload.data, accepted_versions)
    return event_model.model_validate(payload.data)


def outbox_event_payload(event: BaseModel) -> dict[str, Any]:
    """Serialize a governed event model for outbox payload persistence."""
    return event.model_dump(mode="json")


def _require_expected_event_type(data: dict[str, Any], expected_event_type: str) -> None:
    actual = data.get("event_type")
    if not isinstance(actual, str) or not actual.strip():
        raise EventContractValidationError(
            f"event_type is required for governed event {expected_event_type!r}"
        )
    if actual != expected_event_type:
        raise EventContractValidationError(
            f"event_type {actual!r} does not match expected {expected_event_type!r}"
        )


def _require_supported_schema_version(
    data: dict[str, Any],
    accepted_schema_versions: tuple[str, ...],
) -> None:
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise EventContractValidationError("schema_version is required for governed events")
    if schema_version not in accepted_schema_versions:
        accepted = ", ".join(sorted(accepted_schema_versions))
        raise EventContractValidationError(
            f"schema_version {schema_version!r} is not supported; accepted versions: {accepted}"
        )
