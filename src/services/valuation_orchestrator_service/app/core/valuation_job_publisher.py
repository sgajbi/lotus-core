from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.config import KAFKA_VALUATION_JOB_REQUESTED_TOPIC
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer


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
    producer: KafkaProducer

    def publish_job_requested(
        self,
        *,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        self.producer.publish_message(
            topic=KAFKA_VALUATION_JOB_REQUESTED_TOPIC,
            key=key,
            value=value,
            headers=headers,
        )

    def confirm_delivery(self, *, timeout_seconds: int) -> int:
        return self.producer.flush(timeout=timeout_seconds)


def get_valuation_job_publisher() -> ValuationJobPublisher:
    return KafkaValuationJobPublisher(get_kafka_producer())
