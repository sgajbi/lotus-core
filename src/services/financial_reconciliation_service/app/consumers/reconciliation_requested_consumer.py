import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import FinancialReconciliationRequestedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..dtos import ReconciliationRunRequest
from ..repositories import ReconciliationRepository
from ..services import ReconciliationService

logger = logging.getLogger(__name__)
SERVICE_NAME = "financial-reconciliation-requested"


class ReconciliationRequestedConsumer(BaseConsumer):
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
            event = FinancialReconciliationRequestedEvent.model_validate(json.loads(value))
            correlation_id = correlation_id_var.get()
            if correlation_id == "<not-set>":
                correlation_id = event.correlation_id

            async for db in get_async_db_session():
                idempotency_repo = IdempotencyRepository(db)
                if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                    return

                service = ReconciliationService(ReconciliationRepository(db))
                request = ReconciliationRunRequest(
                    portfolio_id=event.portfolio_id,
                    business_date=event.business_date,
                    epoch=event.epoch,
                    requested_by=event.requested_by,
                )
                await service.run_automatic_bundle(
                    request=request,
                    correlation_id=correlation_id,
                    reconciliation_types=event.reconciliation_types,
                )

                await idempotency_repo.mark_event_processed(
                    event_id,
                    event.portfolio_id,
                    SERVICE_NAME,
                    correlation_id,
                )
                await db.commit()

        except (json.JSONDecodeError, ValidationError):
            logger.error("Invalid reconciliation request payload; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error in reconciliation request consumer; retrying.")
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected reconciliation consumer error; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, exc)
