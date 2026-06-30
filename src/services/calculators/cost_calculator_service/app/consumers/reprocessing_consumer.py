# src/services/calculators/cost_calculator_service/app/consumers/reprocessing_consumer.py
import json
import logging
from typing import Any

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)
REPROCESSING_REQUESTED_TOPIC = "transactions.reprocessing.requested"


class ReprocessingPayloadError(ValueError):
    """Raised when a reprocessing request payload is structurally invalid."""


def _message_payload(msg: Message) -> dict[str, Any]:
    payload = json.loads(msg.value().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ReprocessingPayloadError("Reprocessing request payload must be a JSON object.")
    return payload


def _requested_transaction_id(event_data: dict[str, Any]) -> str | None:
    transaction_id = str(event_data.get("transaction_id") or "").strip()
    return transaction_id or None


class ReprocessingConsumer(BaseConsumer):
    """
    Consumes events requesting a transaction reprocessing, and uses the
    ReprocessingRepository to perform the action.
    """

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        """Processes a single reprocessing request."""
        try:
            event_data = _message_payload(msg)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ):
                transaction_id = _requested_transaction_id(event_data)
                if not transaction_id:
                    logger.warning(
                        "Received reprocessing request with no transaction_id. Skipping."
                    )
                    return
                await self._reprocess_transaction(transaction_id)

        except Exception as exc:
            await self._handle_processing_error(msg, exc)

    async def _reprocess_transaction(self, transaction_id: str) -> None:
        logger.info("Processing reprocessing request for transaction_id: %s", transaction_id)
        kafka_producer = get_kafka_producer()
        async for db_session in get_async_db_session():
            # The repository handles its own transaction, no need for one here.
            repo = ReprocessingRepository(db=db_session, kafka_producer=kafka_producer)
            await repo.reprocess_transactions_by_ids([transaction_id])

    async def _handle_processing_error(self, msg: Message, exc: Exception) -> None:
        if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ReprocessingPayloadError)):
            logger.error("Failed to parse reprocessing request. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
            return
        if isinstance(exc, (DBAPIError, OperationalError)):
            logger.warning(
                "Database error while processing reprocessing request: %s. Retrying...",
                exc,
                exc_info=False,
            )
            raise exc
        logger.error("Unexpected error during reprocessing. Sending to DLQ.", exc_info=True)
        await self._send_to_dlq_async(msg, exc)
