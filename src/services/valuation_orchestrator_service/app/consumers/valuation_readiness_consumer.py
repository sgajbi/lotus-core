import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.event_mapping import decode_kafka_event_payload, validate_kafka_event_payload
from portfolio_common.events import PortfolioDayReadyForValuationEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.retry_policy import CONSUMER_DB_SHORT_RETRY, tenacity_retry_kwargs
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry

logger = logging.getLogger(__name__)
SERVICE_NAME = "valuation-readiness-consumer"


class ValuationReadinessConsumer(BaseConsumer):
    @retry(
        **tenacity_retry_kwargs(
            profile=CONSUMER_DB_SHORT_RETRY,
            retry_exceptions=(DBAPIError, IntegrityError),
            logger=logger,
        )
    )
    async def process_message(self, msg: Message):
        try:
            decoded_payload = decode_kafka_event_payload(msg)
            event = validate_kafka_event_payload(
                decoded_payload, PortfolioDayReadyForValuationEvent
            )
            with self._message_correlation_context(msg) as correlation_id:
                async for db in get_async_db_session():
                    async with db.begin():
                        idempotency_repo = IdempotencyRepository(db)
                        if not await idempotency_repo.claim_event_processing(
                            decoded_payload.event_id,
                            event.portfolio_id,
                            SERVICE_NAME,
                            correlation_id,
                        ):
                            return

                        await ValuationJobRepository(db).upsert_job(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            valuation_date=event.valuation_date,
                            epoch=event.epoch,
                            correlation_id=correlation_id,
                        )
        except (json.JSONDecodeError, ValidationError):
            logger.error("Invalid valuation readiness payload; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error in valuation readiness consumer; retrying.")
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected valuation readiness consumer error.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
