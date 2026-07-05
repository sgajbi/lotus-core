import json
import logging

from confluent_kafka import Message
from portfolio_common.event_mapping import decode_kafka_event_payload, validate_kafka_event_payload
from portfolio_common.events import PortfolioAggregationDayCompletedEvent
from portfolio_common.kafka_consumer import BaseConsumer
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..dependencies import get_pipeline_stage_message_handler

logger = logging.getLogger(__name__)


class PortfolioAggregationStageConsumer(BaseConsumer):
    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(8),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        try:
            decoded_payload = decode_kafka_event_payload(msg)
            event = validate_kafka_event_payload(
                decoded_payload, PortfolioAggregationDayCompletedEvent
            )
            with self._message_correlation_context(msg) as correlation_id:
                handler = get_pipeline_stage_message_handler()
                await handler.handle_portfolio_aggregation_completed(
                    event_id=decoded_payload.event_id,
                    event=event,
                    correlation_id=correlation_id,
                )

        except (json.JSONDecodeError, ValidationError):
            logger.error(
                "Invalid portfolio aggregation completion payload; sending to DLQ.",
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error in portfolio aggregation stage consumer; retrying.")
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected orchestrator error; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
