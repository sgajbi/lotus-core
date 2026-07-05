from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.config import KAFKA_VALUATION_JOB_REQUESTED_TOPIC
from portfolio_common.event_publisher import (
    EventPublisher,
    EventPublishRequest,
    get_kafka_event_publisher,
)


class ValuationJobPublishError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, retryable: bool) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.retryable = retryable


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
            infrastructure_error = result.infrastructure_error
            reason_code = (
                infrastructure_error.reason_code
                if infrastructure_error is not None
                else result.status.value
            )
            retryable = (
                infrastructure_error.retryable if infrastructure_error is not None else False
            )
            raise ValuationJobPublishError(
                result.error_message or result.status.value,
                reason_code=reason_code,
                retryable=retryable,
            )

    def confirm_delivery(self, *, timeout_seconds: int) -> int:
        result = self.event_publisher.confirm_delivery(timeout_seconds=timeout_seconds)
        return result.undelivered_count


def get_valuation_job_publisher() -> ValuationJobPublisher:
    return KafkaValuationJobPublisher(get_kafka_event_publisher())
