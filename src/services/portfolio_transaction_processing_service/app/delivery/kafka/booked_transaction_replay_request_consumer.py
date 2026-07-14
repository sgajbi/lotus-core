from __future__ import annotations

import logging

from confluent_kafka import Message
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

from ...application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayStatus,
    ReplayBookedTransactionUseCase,
)
from .booked_transaction_replay_request_mapper import (
    map_booked_transaction_replay_request,
    parse_booked_transaction_replay_request,
)

logger = logging.getLogger(__name__)


class BookedTransactionReplayRequestConsumer(BaseConsumer):
    """Republish one canonical booked transaction for normal combined processing."""

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
        )
        self._use_case = use_case

    async def process_message(self, msg: Message) -> None:
        request = parse_booked_transaction_replay_request(msg.value())
        with self._message_correlation_context(
            msg,
            fallback_correlation_id=request.correlation_id,
        ) as correlation_id:
            command = map_booked_transaction_replay_request(
                request,
                correlation_id=correlation_id,
            )
            if command is None:
                logger.warning(
                    "Booked transaction replay request has no transaction_id; acknowledging.",
                    extra={"replay_status": "invalid_request_acknowledged"},
                )
                return
            try:
                result = await self._use_case.execute(command)
            except BookedTransactionReplayDependencyUnavailable as exc:
                raise RetryableConsumerError(
                    "Booked transaction replay dependency unavailable"
                ) from exc

        if result.status is BookedTransactionReplayStatus.NOT_FOUND:
            logger.warning(
                "Booked transaction replay source was not found; acknowledging.",
                extra={
                    "transaction_id": result.transaction_id,
                    "replay_status": result.status.value,
                },
            )
            return
        logger.info(
            "Booked transaction replay published for combined processing.",
            extra={
                "transaction_id": result.transaction_id,
                "replay_status": result.status.value,
            },
        )
