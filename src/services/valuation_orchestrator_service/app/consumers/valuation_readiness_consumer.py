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


def _readiness_source_mutation_id(outbox_id: int) -> str:
    """Return stable identity for the durable outbox mutation behind readiness."""

    return cast(
        str,
        stable_content_hash(
            {
                "event_type": "PortfolioDayReadyForValuation",
                "outbox_id": str(outbox_id),
            }
        ),
    )


def _readiness_outbox_id(msg: Message) -> int | None:
    """Return an absent legacy sequence or validate a present sequence fail-closed."""

    try:
        headers = msg.headers() or []
    except Exception as exc:
        raise EventContractValidationError(
            "Valuation readiness headers could not be inspected"
        ) from exc
    for name, raw_value in reversed(headers):
        if name != "outbox_id":
            continue
        if isinstance(raw_value, (bytes, bytearray)):
            try:
                value = raw_value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise EventContractValidationError(
                    "Valuation readiness outbox_id must be UTF-8"
                ) from exc
        elif isinstance(raw_value, str):
            value = raw_value
        else:
            raise EventContractValidationError("Valuation readiness outbox_id must be text")
        try:
            outbox_id = int(value.strip())
        except ValueError as exc:
            raise EventContractValidationError(
                "Valuation readiness outbox_id must be a positive integer"
            ) from exc
        if outbox_id <= 0:
            raise EventContractValidationError(
                "Valuation readiness outbox_id must be a positive integer"
            )
        return outbox_id
    return None


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
            readiness_outbox_id = _readiness_outbox_id(msg)
            source_mutation_id = (
                _readiness_source_mutation_id(readiness_outbox_id)
                if readiness_outbox_id is not None
                else None
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

                        job_repository = ValuationJobRepository(db)
                        if readiness_outbox_id is None:
                            await job_repository.upsert_job(
                                portfolio_id=event.portfolio_id,
                                security_id=event.security_id,
                                valuation_date=event.valuation_date,
                                epoch=event.epoch,
                                correlation_id=correlation_id,
                            )
                        else:
                            if source_mutation_id is None:  # pragma: no cover - local parser fence
                                raise RuntimeError("Readiness mutation identity was not resolved")
                            await job_repository.upsert_position_readiness_job(
                                portfolio_id=event.portfolio_id,
                                security_id=event.security_id,
                                valuation_date=event.valuation_date,
                                epoch=event.epoch,
                                correlation_id=correlation_id,
                                source_mutation_id=source_mutation_id,
                                readiness_outbox_id=readiness_outbox_id,
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
