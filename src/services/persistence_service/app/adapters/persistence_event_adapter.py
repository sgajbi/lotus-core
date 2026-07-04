"""Kafka message to persistence event boundary mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from confluent_kafka import Message
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
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


def decode_persistence_message_payload(msg: Message) -> PersistenceMessagePayload:
    """Decode raw Kafka bytes into the payload consumed by persistence event models."""
    data = json.loads(msg.value().decode("utf-8"))
    return PersistenceMessagePayload(
        event_id=persistence_event_id(msg),
        data=data,
        fallback_correlation_id=data.get("correlation_id"),
    )


def validate_persistence_event_payload(
    payload: PersistenceMessagePayload,
    event_model: type[EventT],
) -> PersistenceEventEnvelope[EventT]:
    """Validate decoded payload and derive consumer idempotency metadata."""
    event = event_model.model_validate(payload.data)
    return PersistenceEventEnvelope(
        event_id=payload.event_id,
        event=event,
        idempotency_key=getattr(event, "transaction_id", payload.event_id),
        portfolio_id=getattr(event, "portfolio_id", None) or "N/A",
    )
