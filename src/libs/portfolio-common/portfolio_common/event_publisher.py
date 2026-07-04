from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer


class EventPublishStatus(str, Enum):
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class EventPublishRequest:
    topic: str
    key: str
    value: object
    headers: Sequence[tuple[str, bytes]] | None = None
    outbox_id: str | None = None
    on_delivery: Callable[[str, bool, str | None], None] | None = None


@dataclass(frozen=True, slots=True)
class EventPublishResult:
    status: EventPublishStatus
    error_message: str | None = None
    undelivered_count: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status == EventPublishStatus.SUCCESS


class EventPublisher(Protocol):
    def publish(self, request: EventPublishRequest) -> EventPublishResult: ...

    def confirm_delivery(self, *, timeout_seconds: int) -> EventPublishResult: ...


@dataclass(frozen=True, slots=True)
class KafkaEventPublisher:
    producer: KafkaProducer

    def publish(self, request: EventPublishRequest) -> EventPublishResult:
        try:
            kwargs: dict[str, Any] = {
                "topic": request.topic,
                "key": request.key,
                "value": request.value,
                "headers": list(request.headers) if request.headers is not None else None,
            }
            if request.outbox_id is not None:
                kwargs["outbox_id"] = request.outbox_id
            if request.on_delivery is not None:
                kwargs["on_delivery"] = request.on_delivery
            self.producer.publish_message(**kwargs)
        except BufferError as exc:
            return EventPublishResult(
                status=EventPublishStatus.RETRYABLE_FAILURE,
                error_message=str(exc),
            )
        except Exception as exc:
            return EventPublishResult(
                status=EventPublishStatus.TERMINAL_FAILURE,
                error_message=str(exc),
            )
        return EventPublishResult(status=EventPublishStatus.SUCCESS)

    def confirm_delivery(self, *, timeout_seconds: int) -> EventPublishResult:
        try:
            undelivered_count = int(self.producer.flush(timeout=timeout_seconds) or 0)
        except Exception as exc:
            return EventPublishResult(
                status=EventPublishStatus.UNCERTAIN,
                error_message=str(exc),
                undelivered_count=1,
            )
        if undelivered_count:
            return EventPublishResult(
                status=EventPublishStatus.UNCERTAIN,
                undelivered_count=undelivered_count,
            )
        return EventPublishResult(status=EventPublishStatus.SUCCESS)


def get_kafka_event_publisher() -> EventPublisher:
    return KafkaEventPublisher(get_kafka_producer())
