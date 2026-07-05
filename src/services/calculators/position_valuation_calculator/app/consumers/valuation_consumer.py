# src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py
import json
import logging

from confluent_kafka import Message
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.kafka_consumer import BaseConsumer
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..valuation_processor import ValuationJobProcessor

logger = logging.getLogger(__name__)


class ValuationConsumer(BaseConsumer):
    """
    Consumes scheduled valuation jobs and delegates valid-message valuation workflow.
    """

    def __init__(
        self,
        *args,
        valuation_processor: ValuationJobProcessor | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._valuation_processor = valuation_processor or ValuationJobProcessor()

    @staticmethod
    def _build_processing_event_id(*, msg: Message) -> str:
        return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")
        event_id = None
        event = None

        try:
            event_data = json.loads(value)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioValuationRequiredEvent.model_validate(event_data)
                event_id = self._build_processing_event_id(msg=msg)

                self._log_valuation_job_start(event)
                await self._valuation_processor.process_valid_event(event, event_id, correlation_id)

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Message validation failed for key '%s'. Sending to DLQ.",
                key,
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, exc)
        except (DBAPIError, OperationalError) as exc:
            logger.warning(
                "DB or data availability error for event %s: %s. Retrying...",
                event_id,
                exc,
                exc_info=False,
            )
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error processing message with key '%s'. Sending to DLQ.",
                key,
                exc_info=True,
            )
            if event:
                await self._valuation_processor.mark_failed_after_unexpected_error(event, exc)
            await self._send_to_dlq_async(msg, exc)

    @staticmethod
    def _log_valuation_job_start(event: PortfolioValuationRequiredEvent) -> None:
        logger.info(
            "Processing valuation job for "
            f"{event.security_id} in {event.portfolio_id} "
            f"on {event.valuation_date} for epoch {event.epoch}"
        )
