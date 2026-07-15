"""Kafka delivery adapter for claimed portfolio aggregation jobs."""

from __future__ import annotations

import json
import logging

from confluent_kafka import Message
from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from pydantic import ValidationError

from ..application.portfolio_timeseries import MaterializePortfolioTimeseries
from .portfolio_aggregation_event_mapper import map_portfolio_aggregation_event

logger = logging.getLogger(__name__)


class PortfolioTimeseriesConsumer(BaseConsumer):
    """Map aggregation job events to the portfolio-timeseries application use case."""

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
        use_case: MaterializePortfolioTimeseries,
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
        """Validate one delivery and delegate durable work to the application layer."""

        try:
            event_data = json.loads(_message_value(msg))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioAggregationRequiredEvent.model_validate(event_data)
                result = await self._use_case.execute(
                    map_portfolio_aggregation_event(event, correlation_id=correlation_id)
                )
                logger.info(
                    "Portfolio-timeseries materialization finished.",
                    extra={
                        "portfolio_id": event.portfolio_id,
                        "aggregation_date": event.aggregation_date.isoformat(),
                        "status": result.status.value,
                        "target_epoch": result.target_epoch,
                        "failure_recorded": result.failure_recorded,
                    },
                )
        except (json.JSONDecodeError, ValidationError) as error:
            logger.error("Portfolio aggregation event validation failed.", exc_info=True)
            await self._send_to_dlq_async(msg, error)
        except Exception as error:
            logger.error("Portfolio-timeseries materialization delivery failed.", exc_info=True)
            await self._send_to_dlq_async(msg, error)


def _message_value(msg: Message) -> str:
    value = msg.value()
    if value is None:
        raise ValueError("Portfolio aggregation job payload is missing")
    return value.decode("utf-8")
