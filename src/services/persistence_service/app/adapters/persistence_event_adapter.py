"""Kafka message to persistence event boundary mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from confluent_kafka import Message
from portfolio_common.event_mapping import (
    decode_kafka_event_payload,
    kafka_event_id,
    validate_kafka_event_payload,
)
from pydantic import BaseModel

EventT = TypeVar("EventT", bound=BaseModel)


@dataclass(frozen=True)
class PersistenceMessagePayload:
    """Decoded transport payload plus deterministic Kafka message identity."""

    event_id: str
    data: dict[str, Any]
    fallback_correlation_id: str | None


@dataclass(frozen=True)
class PersistenceEventEnvelope(Generic[EventT]):
    """Validated event plus persistence consumer metadata."""

    event_id: str
    event: EventT
    idempotency_key: str
    portfolio_id: str


def persistence_event_id(msg: Message) -> str:
    """Build the deterministic fallback identity for a Kafka message."""
    return kafka_event_id(msg)


def decode_persistence_message_payload(msg: Message) -> PersistenceMessagePayload:
    """Decode raw Kafka bytes into the payload consumed by persistence event models."""
    decoded = decode_kafka_event_payload(msg)
    return PersistenceMessagePayload(
        event_id=decoded.event_id,
        data=decoded.data,
        fallback_correlation_id=decoded.data.get("correlation_id"),
    )


def validate_persistence_event_payload(
    payload: PersistenceMessagePayload,
    event_model: type[EventT],
) -> PersistenceEventEnvelope[EventT]:
    """Validate decoded payload and derive consumer idempotency metadata."""
    event = validate_kafka_event_payload(payload, event_model)
    return PersistenceEventEnvelope(
        event_id=payload.event_id,
        event=event,
        idempotency_key=getattr(event, "transaction_id", payload.event_id),
        portfolio_id=getattr(event, "portfolio_id", None) or "N/A",
    )
