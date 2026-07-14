from __future__ import annotations

import json
import logging
from typing import cast

from confluent_kafka import Message
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from portfolio_common.logging_utils import (
    normalize_lineage_value,
    traceparent_var,
)
from portfolio_common.reprocessing_replay import (
    TRANSACTION_PROCESSING_INTENT_HEADER,
    TRANSACTION_PROCESSING_REPAIR_VALUE,
)
from sqlalchemy.exc import DBAPIError, IntegrityError

from ...application import (
    ProcessTransactionUseCase,
    TransactionProcessingError,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
)
from .transaction_event_mapper import map_transaction_event

logger = logging.getLogger(__name__)

_ACKNOWLEDGED_REJECTION_REASONS = frozenset({"cashflow_epoch_rejected"})


class TransactionProcessingConsumer(BaseConsumer):
    """Consume each booked transaction once and invoke the atomic processing use case."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: str | None = None,
        service_prefix: str = "SVC",
        metrics: dict[str, object] | None = None,
        execution_profile: KafkaConsumerExecutionProfile | None = None,
        *,
        use_case: ProcessTransactionUseCase,
    ) -> None:
        super().__init__(
            bootstrap_servers=bootstrap_servers,
            topic=topic,
            group_id=group_id,
            dlq_topic=dlq_topic,
            service_prefix=service_prefix,
            metrics=metrics,
            execution_profile=execution_profile,
        )
        self._use_case = use_case

    async def process_message(self, msg: Message) -> None:
        event_id = _message_event_id(msg)
        data = json.loads(_message_value(msg))
        with self._message_correlation_context(
            msg,
            fallback_correlation_id=data.get("correlation_id"),
        ) as correlation_id:
            event = TransactionEvent.model_validate(data)
            command = map_transaction_event(
                event,
                event_id=event_id,
                correlation_id=correlation_id,
                traceparent=_message_traceparent(self, msg),
                processing_intent=_message_processing_intent(msg),
            )
            try:
                result = await self._use_case.execute(command)
            except TransactionProcessingRejected as exc:
                if exc.reason_code in _ACKNOWLEDGED_REJECTION_REASONS:
                    _log_acknowledged_rejection(event, event_id, exc)
                    return
                raise
            except TransactionProcessingError as exc:
                if exc.retryable:
                    raise RetryableConsumerError(
                        f"Transaction processing dependency unavailable: {exc.reason_code}"
                    ) from exc
                raise
            except (DBAPIError, IntegrityError) as exc:
                raise RetryableConsumerError(
                    "Transaction processing database dependency unavailable"
                ) from exc

        logger.info(
            "Transaction processing completed.",
            extra={
                "event_id": event_id,
                "portfolio_id": event.portfolio_id,
                "transaction_id": event.transaction_id,
                "processing_status": result.status.value,
                "position_record_count": result.position_record_count,
                "cashflow_record_count": result.cashflow_record_count,
                "replay_queued_count": result.replay_queued_count,
            },
        )


def _message_value(msg: Message) -> str:
    value = msg.value()
    if value is None:
        raise ValueError("Transaction processing message payload is missing")
    return str(value.decode("utf-8"))


def _message_event_id(msg: Message) -> str:
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


def _message_traceparent(consumer: BaseConsumer, msg: Message) -> str | None:
    context_traceparent = cast(str | None, normalize_lineage_value(traceparent_var.get()))
    if context_traceparent is not None:
        return context_traceparent
    header_traceparent = consumer._get_message_header_traceparent(msg)
    return cast(
        str | None,
        normalize_lineage_value(
            str(header_traceparent) if header_traceparent is not None else None
        ),
    )


def _message_processing_intent(msg: Message) -> TransactionProcessingIntent:
    intent_values = [
        value
        for key, value in msg.headers() or []
        if key.strip().lower() == TRANSACTION_PROCESSING_INTENT_HEADER
    ]
    if not intent_values:
        return TransactionProcessingIntent.STANDARD
    if intent_values != [TRANSACTION_PROCESSING_REPAIR_VALUE]:
        raise ValueError("Transaction processing intent header is invalid")
    return TransactionProcessingIntent.REPAIR


def _log_acknowledged_rejection(
    event: TransactionEvent,
    event_id: str,
    error: TransactionProcessingRejected,
) -> None:
    logger.info(
        "Transaction processing event rejected by current epoch fence.",
        extra={
            "event_id": event_id,
            "portfolio_id": event.portfolio_id,
            "transaction_id": event.transaction_id,
            "reason_code": error.reason_code,
            "processing_status": "rejected",
        },
    )
