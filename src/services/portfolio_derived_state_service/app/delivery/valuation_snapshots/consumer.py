"""Kafka delivery adapter for authoritative valuation snapshot events."""

from __future__ import annotations

import json
import logging

from confluent_kafka import Message
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ...application.position_timeseries import MaterializePositionTimeseries
from .mapper import map_position_snapshot_event

logger = logging.getLogger(__name__)


class PositionTimeseriesConsumer(BaseConsumer):
    """Map valuation snapshot events to the position-timeseries application use case."""

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
        use_case: MaterializePositionTimeseries,
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
        """Retry transient integrity races and terminally route exhausted delivery."""

        retry_config = retry(
            wait=wait_fixed(3),
            stop=stop_after_attempt(15),
            before=before_log(logger, logging.INFO),
            retry=retry_if_exception_type(IntegrityError),
        )
        try:
            await retry_config(self._process_message_with_retry)(msg)
        except Exception as error:
            logger.error(
                "Position-timeseries delivery exhausted retries for %s-%s-%s.",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, error)

    async def _process_message_with_retry(self, msg: Message) -> None:
        try:
            event_data = json.loads(_message_value(msg))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = DailyPositionSnapshotPersistedEvent.model_validate(event_data)
                result = await self._use_case.execute(
                    map_position_snapshot_event(event, correlation_id=correlation_id)
                )
                logger.info(
                    "Position-timeseries materialization completed.",
                    extra={
                        "snapshot_id": event.id,
                        "portfolio_id": event.portfolio_id,
                        "security_id": event.security_id,
                        "valuation_date": event.date.isoformat(),
                        "epoch": event.epoch,
                        "snapshot_found": result.snapshot_found,
                        "current_day_changed": result.current_day_changed,
                        "dependent_days_changed": result.dependent_days_changed,
                        "dependent_propagation_truncated": (result.dependent_propagation_truncated),
                    },
                )
        except (json.JSONDecodeError, ValidationError) as error:
            logger.error("Position snapshot event validation failed.", exc_info=True)
            await self._send_to_dlq_async(msg, error)
        except IntegrityError:
            logger.warning("Position-timeseries persistence raced; retrying.", exc_info=True)
            raise
        except Exception as error:
            logger.error("Position-timeseries materialization failed.", exc_info=True)
            await self._send_to_dlq_async(msg, error)


def _message_value(msg: Message) -> str:
    value = msg.value()
    if value is None:
        raise ValueError("Position snapshot event payload is missing")
    if not isinstance(value, bytes):
        raise TypeError("Position snapshot event payload must be bytes")
    return value.decode("utf-8")
