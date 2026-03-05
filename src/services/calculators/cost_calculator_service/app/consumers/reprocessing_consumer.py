# src/services/calculators/cost_calculator_service/app/consumers/reprocessing_consumer.py
import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.reprocessing_repository import ReprocessingRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)
REPROCESSING_REQUESTED_TOPIC = "transactions_reprocessing_requested"

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
        reraise=True
    )
    async def process_message(self, msg: Message):
        """Processes a single reprocessing request."""
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            transaction_id = event_data.get("transaction_id")

            if not transaction_id:
                logger.warning("Received reprocessing request with no transaction_id. Skipping.")
                return

            logger.info(f"Processing reprocessing request for transaction_id: {transaction_id}")
            
            kafka_producer = get_kafka_producer()
            async for db_session in get_async_db_session():
                # The repository handles its own transaction, no need for one here.
                repo = ReprocessingRepository(db=db_session, kafka_producer=kafka_producer)
                await repo.reprocess_transactions_by_ids([transaction_id])

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Failed to parse reprocessing request. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError) as e:
            logger.warning(f"Database error while processing reprocessing request: {e}. Retrying...", exc_info=False)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during reprocessing for transaction_id '{event_data.get('transaction_id')}'. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)