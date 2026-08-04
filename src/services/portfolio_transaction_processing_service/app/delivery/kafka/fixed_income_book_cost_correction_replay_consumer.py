"""Kafka delivery for deterministic fixed-income book-cost correction replay."""

from __future__ import annotations

import json
import logging

from confluent_kafka import Message
from portfolio_common.event_contracts import (
    FixedIncomeBookCostDisposalReplayRequestedEvent,
)
from portfolio_common.event_mapping import (
    DecodedKafkaEventPayload,
    kafka_event_id,
    validate_kafka_event_payload,
)
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

from ...application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayStatus,
    ReplayBookedTransactionCommand,
    ReplayBookedTransactionUseCase,
)
from ...application.fixed_income_book_cost import (
    map_fixed_income_book_cost_disposal_replay_event,
)

logger = logging.getLogger(__name__)

_EVENT_TYPE = "fixed_income.book_cost.disposal_replay.requested"
_ACCEPTED_SCHEMA_VERSIONS = ("1.0.0",)


class FixedIncomeBookCostCorrectionReplaySourceMissing(ValueError):
    """Raised when a durable correction references no canonical booked transaction."""


class FixedIncomeBookCostCorrectionReplayConsumer(BaseConsumer):
    """Replay one earliest source-lot anchor with stable command idempotency."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: str | None = None,
        service_prefix: str = "BOOKCOSTREPLAY",
        metrics: dict[str, object] | None = None,
        execution_profile: KafkaConsumerExecutionProfile | None = None,
        retryable_failure_max_attempts: int | None = None,
        retryable_failure_max_elapsed_seconds: int | None = None,
        *,
        use_case: ReplayBookedTransactionUseCase,
    ) -> None:
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic=topic,
            group_id=group_id,
            dlq_topic=dlq_topic,
            service_prefix=service_prefix,
            metrics=metrics,
            execution_profile=execution_profile,
            retryable_failure_max_attempts=retryable_failure_max_attempts,
            retryable_failure_max_elapsed_seconds=retryable_failure_max_elapsed_seconds,
        )
        self._use_case = use_case

    async def process_message(self, msg: Message) -> None:
        event = validate_kafka_event_payload(
            _message_payload(msg),
            FixedIncomeBookCostDisposalReplayRequestedEvent,
            expected_event_type=_EVENT_TYPE,
            accepted_schema_versions=_ACCEPTED_SCHEMA_VERSIONS,
        )
        if self._message_key_text(msg) != event.partition_key:
            raise ValueError(
                "fixed-income book-cost correction replay partition key does not match event scope"
            )
        intent = map_fixed_income_book_cost_disposal_replay_event(event)
        with self._message_correlation_context(
            msg,
            fallback_correlation_id=event.correlation_id,
        ) as correlation_id:
            try:
                result = await self._use_case.execute(
                    ReplayBookedTransactionCommand(
                        transaction_id=intent.anchor.transaction_id,
                        correlation_id=correlation_id,
                        repair_delivery_id=intent.command_id,
                    )
                )
            except BookedTransactionReplayDependencyUnavailable as exc:
                raise RetryableConsumerError(
                    "Fixed-income book-cost correction replay dependency unavailable"
                ) from exc

        if result.status is BookedTransactionReplayStatus.NOT_FOUND:
            raise FixedIncomeBookCostCorrectionReplaySourceMissing(
                "fixed-income book-cost correction replay source transaction was not found: "
                f"{result.transaction_id}"
            )
        logger.info(
            "Fixed-income book-cost correction replay published.",
            extra={
                "command_id": intent.command_id,
                "lot_id": intent.scope.lot_id,
                "portfolio_id": intent.scope.portfolio_id,
                "security_id": intent.scope.security_id,
                "transaction_id": result.transaction_id,
            },
        )


def _message_payload(msg: Message) -> DecodedKafkaEventPayload:
    value = msg.value()
    if value is None:
        raise ValueError("fixed-income book-cost correction replay payload is missing")
    try:
        data = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "fixed-income book-cost correction replay payload is not valid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("fixed-income book-cost correction replay payload must be a JSON object")
    return DecodedKafkaEventPayload(event_id=kafka_event_id(msg), data=data)
