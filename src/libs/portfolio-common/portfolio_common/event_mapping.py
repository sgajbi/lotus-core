"""Shared event mapping helpers for Kafka and outbox boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from confluent_kafka import Message
from pydantic import BaseModel

EventT = TypeVar("EventT", bound=BaseModel)


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
) -> EventT:
    """Validate a decoded Kafka payload against a governed event model."""
    return event_model.model_validate(payload.data)


def outbox_event_payload(event: BaseModel) -> dict[str, Any]:
    """Serialize a governed event model for outbox payload persistence."""
    return event.model_dump(mode="json")
