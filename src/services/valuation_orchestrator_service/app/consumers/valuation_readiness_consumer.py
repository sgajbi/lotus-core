import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioDayReadyForValuationEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)
SERVICE_NAME = "valuation-readiness-consumer"


class ValuationReadinessConsumer(BaseConsumer):
    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(8),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
        reraise=True,
    )
    async def process_message(self, msg: Message):
        value = msg.value().decode("utf-8")
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

        try:
            event = PortfolioDayReadyForValuationEvent.model_validate(json.loads(value))
            with self._message_correlation_context(msg) as correlation_id:
                async for db in get_async_db_session():
                    async with db.begin():
                        idempotency_repo = IdempotencyRepository(db)
                        if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                            return

                        await ValuationJobRepository(db).upsert_job(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            valuation_date=event.valuation_date,
                            epoch=event.epoch,
                            correlation_id=correlation_id,
                        )
                        await idempotency_repo.mark_event_processed(
                            event_id,
                            event.portfolio_id,
                            SERVICE_NAME,
                            correlation_id,
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
