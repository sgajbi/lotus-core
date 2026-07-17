"""Kafka adapter for source-owned persisted FX observations."""

from __future__ import annotations

import json
import logging

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.event_mapping import (
    EventContractValidationError,
    decode_kafka_event_payload,
    validate_kafka_event_payload,
)
from portfolio_common.events import FxRatePersistedEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.retry_policy import CONSUMER_DB_SHORT_RETRY, tenacity_retry_kwargs
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import retry

from ...application.process_fx_rate_correction import ProcessFxRateCorrection
from ...domain.fx_revaluation import DirectCurrencyPair, FxRateCorrection
from ...infrastructure.repositories.fx_revaluation_repository import (
    SqlAlchemyFxRevaluationRepository,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "fx-rate-revaluation-trigger"


def _fallback_correlation_id(event_data: dict[str, object]) -> str:
    observation_id = str(event_data.get("observation_id", "unknown"))
    return f"FX_RATE_EVENT_{observation_id.removeprefix('sha256:')[:16]}"


def _correction_from_event(event: FxRatePersistedEvent) -> FxRateCorrection:
    return FxRateCorrection(
        pair=DirectCurrencyPair(event.from_currency, event.to_currency),
        effective_date=event.rate_date,
        content_hash=event.content_hash,
        generated_at=event.generated_at,
    )


class FxRatePersistedConsumer(BaseConsumer):
    """Consume persisted FX evidence and stage bounded valuation correction work."""

    @retry(  # type: ignore[untyped-decorator]
        **tenacity_retry_kwargs(
            profile=CONSUMER_DB_SHORT_RETRY,
            retry_exceptions=(DBAPIError, OperationalError),
            logger=logger,
        )
    )
    async def process_message(self, msg: Message) -> None:
        """Validate and process one persisted FX observation transactionally."""
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        event: FxRatePersistedEvent | None = None
        try:
            decoded_payload = decode_kafka_event_payload(msg)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=_fallback_correlation_id(decoded_payload.data),
            ) as correlation_id:
                event = validate_kafka_event_payload(
                    decoded_payload,
                    FxRatePersistedEvent,
                    expected_event_type="FxRatePersisted",
                )
                async for db in get_async_db_session():
                    async with db.begin():
                        idempotency = IdempotencyRepository(db)
                        if not await idempotency.claim_event_processing(
                            event.observation_id,
                            "N/A",
                            SERVICE_NAME,
                            correlation_id,
                        ):
                            logger.info(
                                "Persisted FX observation already processed; skipping replay.",
                                extra={"observation_id": event.observation_id},
                            )
                            return

                        handler = ProcessFxRateCorrection(
                            repository=SqlAlchemyFxRevaluationRepository(db),
                            valuation_jobs=ValuationJobRepository(db),
                        )
                        plan = await handler.execute(
                            correction=_correction_from_event(event),
                            correlation_id=correlation_id,
                            source_correction_id=event.observation_id,
                        )
                        logger.info(
                            "Persisted FX observation staged for valuation correction.",
                            extra={
                                "currency_pair": plan.pair.key,
                                "effective_date": plan.effective_date.isoformat(),
                                "immediate_job_count": plan.immediate_job_count,
                            },
                        )
        except (json.JSONDecodeError, ValidationError, EventContractValidationError):
            logger.error("Persisted FX event validation failed for key '%s'.", key, exc_info=True)
            raise
        except (DBAPIError, OperationalError):
            logger.warning(
                "Database error while processing persisted FX observation; retrying.",
                exc_info=False,
                extra={
                    "observation_id": event.observation_id if event is not None else None,
                },
            )
            raise
        except Exception:
            logger.error(
                "Unexpected error processing persisted FX event with key '%s'.",
                key,
                exc_info=True,
            )
            raise
