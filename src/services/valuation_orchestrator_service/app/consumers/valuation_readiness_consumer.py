import json
import logging
from typing import cast

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.event_mapping import (
    EventContractValidationError,
    decode_kafka_event_payload,
    validate_kafka_event_payload,
)
from portfolio_common.events import PortfolioDayReadyForValuationEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.retry_policy import CONSUMER_DB_SHORT_RETRY, tenacity_retry_kwargs
from portfolio_common.source_data_product_metadata import stable_content_hash
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry

logger = logging.getLogger(__name__)
SERVICE_NAME = "valuation-readiness-consumer"


def _readiness_source_mutation_id(event: PortfolioDayReadyForValuationEvent) -> str | None:
    """Return transport-neutral identity for the transaction mutation behind readiness."""

    if event.source_transaction_id is None:
        return None
    return cast(
        str,
        stable_content_hash(
            {
                "portfolio_id": event.portfolio_id,
                "security_id": event.security_id,
                "valuation_date": event.valuation_date,
                "epoch": event.epoch,
                "source_transaction_id": event.source_transaction_id,
            }
        ),
    )


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
                decoded_payload,
                PortfolioDayReadyForValuationEvent,
                expected_event_type="PortfolioDayReadyForValuation",
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

                        source_mutation_id = _readiness_source_mutation_id(event)
                        await ValuationJobRepository(db).upsert_job(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            valuation_date=event.valuation_date,
                            epoch=event.epoch,
                            correlation_id=correlation_id,
                            source_correction_id=source_mutation_id,
                            rearm_completed=True,
                            requeue_if_processing=source_mutation_id is not None,
                        )
        except (json.JSONDecodeError, ValidationError, EventContractValidationError):
            logger.error("Invalid valuation readiness payload.", exc_info=True)
            raise
        except (DBAPIError, IntegrityError):
            logger.warning("DB error in valuation readiness consumer; retrying.")
            raise
        except Exception:  # pragma: no cover - defensive
            logger.error("Unexpected valuation readiness consumer error.", exc_info=True)
            raise
