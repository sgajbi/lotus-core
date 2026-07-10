import json
import logging
from typing import cast

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .cost_calculation_processor import (
    CostCalculationEventProcessor,
    CostCalculationProcessorDependencyFactory,
    PortfolioNotFoundError,
)
from .cost_calculation_workflow import (
    LOT_OPENING_BEHAVIORS,
    CostCalculationWorkflow,
    FxRateNotFoundError,
    InstrumentReferenceUnavailableError,
    OpenLotStateUpdateScope,
    UpstreamCashLegUnavailableError,
    _normalize_event_code,
    _normalize_fee_amount,
)

__all__ = [
    "LOT_OPENING_BEHAVIORS",
    "CostCalculationWorkflow",
    "CostCalculatorConsumer",
    "FxRateNotFoundError",
    "InstrumentReferenceUnavailableError",
    "OpenLotStateUpdateScope",
    "PortfolioNotFoundError",
    "UpstreamCashLegUnavailableError",
    "_normalize_fee_amount",
]

logger = logging.getLogger(__name__)


def _message_value(msg: Message) -> str:
    return cast(bytes, msg.value()).decode("utf-8")


def _message_event_id(msg: Message) -> str:
    return f"{msg.topic()}-{msg.partition()}-{msg.offset()}"


class CostCalculatorConsumer(CostCalculationWorkflow, BaseConsumer):
    """Compatibility delivery shell retained only while legacy delivery tests are migrated."""

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, PortfolioNotFoundError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        event = None

        try:
            data = json.loads(_message_value(msg))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=data.get("correlation_id"),
            ) as correlation_id:
                event = TransactionEvent.model_validate(data)
                await self._process_valid_cost_event(
                    event=event,
                    event_id=_message_event_id(msg),
                    correlation_id=correlation_id,
                )
        except Exception as exc:
            await self._handle_process_message_error(msg, event, exc)

    async def _process_valid_cost_event(
        self,
        *,
        event: TransactionEvent,
        event_id: str,
        correlation_id: str,
    ) -> None:
        dependency_factory = CostCalculationProcessorDependencyFactory()
        processor = CostCalculationEventProcessor(self)
        async for db in get_async_db_session():
            async with db.begin():
                await processor.process_valid_event(
                    event=event,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    dependencies=dependency_factory.from_session(db),
                )

    async def _handle_process_message_error(
        self,
        msg: Message,
        event: TransactionEvent | None,
        exc: Exception,
    ) -> None:
        if isinstance(exc, (json.JSONDecodeError, ValidationError)):
            logger.error("Invalid TransactionEvent; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
            return
        if isinstance(
            exc,
            (
                FxRateNotFoundError,
                UpstreamCashLegUnavailableError,
                InstrumentReferenceUnavailableError,
            ),
        ):
            self._record_process_message_failure(event, "retryable_error")
            logger.warning("Required reference data is not available; deferring message.")
            raise RetryableConsumerError(str(exc))
        if isinstance(exc, (DBAPIError, IntegrityError, PortfolioNotFoundError)):
            self._record_process_message_failure(event, "retryable_error")
            logger.warning("DB or data availability error; will retry...", exc_info=True)
            raise exc
        self._record_process_message_failure(event, "failed")
        transaction_id = getattr(event, "transaction_id", "UNKNOWN")
        logger.error(
            "Unexpected error processing transaction %s. Sending to DLQ.",
            transaction_id,
            exc_info=True,
        )
        await self._send_to_dlq_async(msg, exc)

    @staticmethod
    def _record_process_message_failure(event: TransactionEvent | None, status: str) -> None:
        BUY_LIFECYCLE_STAGE_TOTAL.labels("process_message", status).inc()
        if _normalize_event_code(getattr(event, "transaction_type", "")) == "SELL":
            SELL_LIFECYCLE_STAGE_TOTAL.labels("process_message", status).inc()
