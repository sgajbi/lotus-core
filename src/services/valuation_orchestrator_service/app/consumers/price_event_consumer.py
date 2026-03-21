# src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py
import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..repositories.instrument_reprocessing_state_repository import (
    InstrumentReprocessingStateRepository,
)
from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "price-event-reprocessing-trigger"


class PriceEventConsumer(BaseConsumer):
    """
    Consumes market price events. If a price is back-dated, it flags the
    instrument by upserting a record to the instrument_reprocessing_state table.
    This acts as a trigger for the ValuationScheduler.
    """

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
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        event = None

        try:
            event_data = json.loads(value)
            price_event_correlation_id = (
                "PRICE_EVENT_"
                f"{event_data.get('security_id', 'unknown')}_"
                f"{event_data.get('price_date', 'unknown')}"
            )
            with self._message_correlation_context(
                msg, fallback_correlation_id=price_event_correlation_id
            ) as correlation_id:
                event = MarketPricePersistedEvent.model_validate(event_data)
                logger.info(
                    f"Received new market price for {event.security_id} on {event.price_date}."
                )

                async for db in get_async_db_session():
                    async with db.begin():
                        idempotency_repo = IdempotencyRepository(db)
                        valuation_repo = ValuationRepository(db)
                        reprocessing_repo = InstrumentReprocessingStateRepository(db)

                        if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                            logger.warning(
                                f"Event {event_id} already processed by {SERVICE_NAME}. Skipping."
                            )
                            return

                        latest_business_date = await valuation_repo.get_latest_business_date()
                        event_correlation_id = correlation_id

                        if latest_business_date and event.price_date <= latest_business_date:
                            open_position_keys = (
                                await valuation_repo.find_open_position_keys_for_security_on_date(
                                    event.security_id, event.price_date
                                )
                            )
                            for portfolio_id, security_id, epoch in open_position_keys:
                                await ValuationJobRepository(db).upsert_job(
                                    portfolio_id=portfolio_id,
                                    security_id=security_id,
                                    valuation_date=event.price_date,
                                    epoch=epoch,
                                    correlation_id=event_correlation_id,
                                )
                            if open_position_keys:
                                logger.info(
                                    "Queued immediate valuation jobs for market price event.",
                                    extra={
                                        "security_id": event.security_id,
                                        "price_date": event.price_date,
                                        "job_count": len(open_position_keys),
                                    },
                                )

                        is_backdated = (
                            latest_business_date and event.price_date < latest_business_date
                        )
                        needs_deferred_reprocessing = (
                            latest_business_date is None or event.price_date > latest_business_date
                        )
                        if is_backdated:
                            logger.warning(
                                "Back-dated price event detected. "
                                "Flagging instrument for reprocessing.",
                                extra={
                                    "security_id": event.security_id,
                                    "price_date": event.price_date,
                                },
                            )
                            await reprocessing_repo.upsert_state(
                                security_id=event.security_id,
                                price_date=event.price_date,
                                correlation_id=event_correlation_id,
                            )
                        elif needs_deferred_reprocessing:
                            logger.info(
                                "Price event is ahead of current business-date horizon. "
                                "Staging durable reprocessing trigger.",
                                extra={
                                    "security_id": event.security_id,
                                    "price_date": event.price_date,
                                    "latest_business_date": latest_business_date,
                                },
                            )
                            await reprocessing_repo.upsert_state(
                                security_id=event.security_id,
                                price_date=event.price_date,
                                correlation_id=event_correlation_id,
                            )

                        await idempotency_repo.mark_event_processed(
                            event_id, "N/A", SERVICE_NAME, event_correlation_id
                        )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                f"Message validation failed for key '{key}'. Sending to DLQ.", exc_info=True
            )
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError) as e:
            logger.warning(
                "Database error while processing price event for "
                f"{getattr(event, 'security_id', 'Unknown')}: {e}. Retrying...",
                exc_info=False,
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing message with key '{key}'. Sending to DLQ.",
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)
