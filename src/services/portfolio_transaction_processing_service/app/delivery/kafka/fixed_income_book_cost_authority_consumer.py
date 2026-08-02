"""Kafka delivery for source-owned fixed-income book-cost authority."""

from __future__ import annotations

import json
import logging
from typing import cast

from confluent_kafka import Message
from portfolio_common.event_contracts import FixedIncomeBookCostAuthorityEvent
from portfolio_common.event_mapping import (
    DecodedKafkaEventPayload,
    kafka_event_id,
    validate_kafka_event_payload,
)
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from sqlalchemy.exc import DBAPIError, IntegrityError

from ...application.fixed_income_book_cost import (
    HandleFixedIncomeBookCostAuthorityEventUseCase,
)

logger = logging.getLogger(__name__)

_EVENT_TYPE = "fixed_income.book_cost.authority.received"
_ACCEPTED_SCHEMA_VERSIONS = ("1.0.0",)


class FixedIncomeBookCostAuthorityConsumer(BaseConsumer):
    """Persist and materialize each exact-scope authority event atomically."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: str | None = None,
        service_prefix: str = "BOOKCOST",
        metrics: dict[str, object] | None = None,
        execution_profile: KafkaConsumerExecutionProfile | None = None,
        retryable_failure_max_attempts: int | None = None,
        retryable_failure_max_elapsed_seconds: int | None = None,
        *,
        use_case: HandleFixedIncomeBookCostAuthorityEventUseCase,
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
        payload = _message_payload(msg)
        event = validate_kafka_event_payload(
            payload,
            FixedIncomeBookCostAuthorityEvent,
            expected_event_type=_EVENT_TYPE,
            accepted_schema_versions=_ACCEPTED_SCHEMA_VERSIONS,
        )
        actual_key = _message_key(msg)
        if actual_key != event.partition_key:
            raise ValueError(
                "fixed-income book-cost authority partition key does not match event scope"
            )
        with self._message_correlation_context(msg):
            try:
                result = await self._use_case.execute(event)
            except (DBAPIError, IntegrityError) as exc:
                raise RetryableConsumerError(
                    "Fixed-income book-cost database dependency unavailable"
                ) from exc
        logger.debug(
            "Fixed-income book-cost authority processed.",
            extra={
                "authority_type": event.authority.authority_type,
                "lot_id": result.scope.lot_id,
                "materialization_outcome": result.materialization.outcome.value,
                "portfolio_id": result.scope.portfolio_id,
                "profile_version": result.materialization.profile_version,
                "security_id": result.scope.security_id,
                "source_version": event.authority.header.source.source_version,
            },
        )


def _message_payload(msg: Message) -> DecodedKafkaEventPayload:
    value = msg.value()
    if value is None:
        raise ValueError("fixed-income book-cost authority payload is missing")
    try:
        data = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("fixed-income book-cost authority payload is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("fixed-income book-cost authority payload must be a JSON object")
    return DecodedKafkaEventPayload(event_id=kafka_event_id(msg), data=data)


def _message_key(msg: Message) -> str:
    key = msg.key()
    if key is None:
        raise ValueError("fixed-income book-cost authority partition key is missing")
    try:
        return cast(str, key.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("fixed-income book-cost authority partition key is not UTF-8") from exc
