from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.config import KAFKA_VALUATION_JOB_REQUESTED_TOPIC
from portfolio_common.event_publisher import (
    EventPublisher,
    EventPublishRequest,
    get_kafka_event_publisher,
)


class ValuationJobPublisher(Protocol):
    def publish_job_requested(
        self,
        *,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None: ...

    def confirm_delivery(self, *, timeout_seconds: int) -> int: ...


@dataclass(frozen=True)
class KafkaValuationJobPublisher:
    event_publisher: EventPublisher

    def publish_job_requested(
        self,
        *,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        result = self.event_publisher.publish(
            EventPublishRequest(
                topic=KAFKA_VALUATION_JOB_REQUESTED_TOPIC,
                key=key,
                value=value,
                headers=headers,
            )
        )
        if not result.succeeded:
            raise RuntimeError(result.error_message or result.status.value)

    def confirm_delivery(self, *, timeout_seconds: int) -> int:
        result = self.event_publisher.confirm_delivery(timeout_seconds=timeout_seconds)
        return result.undelivered_count


def get_valuation_job_publisher() -> ValuationJobPublisher:
    return KafkaValuationJobPublisher(get_kafka_event_publisher())
