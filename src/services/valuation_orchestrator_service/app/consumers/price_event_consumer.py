# src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py
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
from portfolio_common.events import MarketPricePersistedEvent, event_business_payload
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.retry_policy import CONSUMER_DB_SHORT_RETRY, tenacity_retry_kwargs
from portfolio_common.source_data_product_metadata import stable_content_hash
from portfolio_common.valuation_job_repository import ValuationJobRepository
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import retry

from ..domain.source_revaluation import (
    SourceRevaluationSchedule,
    decide_source_revaluation_schedule,
)
from ..repositories.instrument_reprocessing_state_repository import (
    InstrumentReprocessingStateRepository,
)
from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "price-event-reprocessing-trigger"


def _price_event_correlation_id(event_data: dict) -> str:
    return (
        "PRICE_EVENT_"
        f"{event_data.get('security_id', 'unknown')}_"
        f"{event_data.get('price_date', 'unknown')}"
    )


def _price_source_correction_id(event: MarketPricePersistedEvent) -> str:
    """Return transport-neutral identity for the accepted price content."""

    return stable_content_hash(event_business_payload(event))


class PriceEventConsumer(BaseConsumer):
    """
    Consumes market price events. If a price is back-dated, it flags the
    instrument by upserting a record to the instrument_reprocessing_state table.
    This acts as a trigger for the ValuationScheduler.
    """

    @retry(
        **tenacity_retry_kwargs(
            profile=CONSUMER_DB_SHORT_RETRY,
            retry_exceptions=(DBAPIError, OperationalError),
            logger=logger,
        )
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        event = None

        try:
            decoded_payload = decode_kafka_event_payload(msg)
            price_event_correlation_id = _price_event_correlation_id(decoded_payload.data)
            with self._message_correlation_context(
                msg, fallback_correlation_id=price_event_correlation_id
            ) as correlation_id:
                event = validate_kafka_event_payload(
                    decoded_payload,
                    MarketPricePersistedEvent,
                    expected_event_type="MarketPricePersisted",
                )
                logger.info(
                    f"Received new market price for {event.security_id} on {event.price_date}."
                )

                async for db in get_async_db_session():
                    async with db.begin():
                        idempotency_repo = IdempotencyRepository(db)
                        valuation_repo = ValuationRepository(db)
                        reprocessing_repo = InstrumentReprocessingStateRepository(db)

                        if not await idempotency_repo.claim_event_processing(
                            decoded_payload.event_id,
                            "N/A",
                            SERVICE_NAME,
                            correlation_id,
                        ):
                            logger.warning(
                                "Event "
                                f"{decoded_payload.event_id} already processed by "
                                f"{SERVICE_NAME}. Skipping."
                            )
                            return

                        latest_business_date = await valuation_repo.get_latest_business_date()
                        event_correlation_id = correlation_id
                        schedule = decide_source_revaluation_schedule(
                            effective_date=event.price_date,
                            latest_business_date=latest_business_date,
                        )

                        open_position_keys = await self._queue_immediate_valuation_jobs(
                            valuation_repo=valuation_repo,
                            job_repo=ValuationJobRepository(db),
                            event=event,
                            schedule=schedule,
                            correlation_id=event_correlation_id,
                            source_correction_id=_price_source_correction_id(event),
                        )

                        await self._stage_reprocessing_if_needed(
                            reprocessing_repo=reprocessing_repo,
                            event=event,
                            schedule=schedule,
                            open_position_keys=open_position_keys,
                            correlation_id=event_correlation_id,
                        )

        except (json.JSONDecodeError, ValidationError, EventContractValidationError):
            logger.error(f"Message validation failed for key '{key}'.", exc_info=True)
            raise
        except (DBAPIError, OperationalError) as e:
            logger.warning(
                "Database error while processing price event for "
                f"{getattr(event, 'security_id', 'Unknown')}: {e}. Retrying...",
                exc_info=False,
            )
            raise
        except Exception:
            logger.error(
                f"Unexpected error processing message with key '{key}'.",
                exc_info=True,
            )
            raise

    async def _queue_immediate_valuation_jobs(
        self,
        *,
        valuation_repo: ValuationRepository,
        job_repo: ValuationJobRepository,
        event: MarketPricePersistedEvent,
        schedule: SourceRevaluationSchedule,
        correlation_id: str,
        source_correction_id: str,
    ) -> list[tuple[str, str, int]]:
        if not schedule.scan_visible_positions:
            return []

        open_position_keys = cast(
            list[tuple[str, str, int]],
            await valuation_repo.find_position_keys_requiring_price_revaluation(
                event.security_id, event.price_date
            ),
        )
        for portfolio_id, security_id, epoch in open_position_keys:
            await job_repo.upsert_job(
                portfolio_id=portfolio_id,
                security_id=security_id,
                valuation_date=event.price_date,
                epoch=epoch,
                correlation_id=correlation_id,
                source_correction_id=source_correction_id,
                requeue_if_processing=True,
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
        return open_position_keys

    async def _stage_reprocessing_if_needed(
        self,
        *,
        reprocessing_repo: InstrumentReprocessingStateRepository,
        event: MarketPricePersistedEvent,
        schedule: SourceRevaluationSchedule,
        open_position_keys: list[tuple[str, str, int]],
        correlation_id: str,
    ) -> None:
        if not schedule.stage_durable_replay:
            if not open_position_keys:
                logger.info(
                    "Current price has no visible positions; later position readiness "
                    "will use the persisted price.",
                    extra={
                        "security_id": event.security_id,
                        "price_date": event.price_date,
                    },
                )
            return

        logger.warning(
            "Effective-dated price requires durable reprocessing.",
            extra={
                "security_id": event.security_id,
                "price_date": event.price_date,
                "revaluation_timing": schedule.timing.value,
            },
        )
        await self._upsert_reprocessing_state(
            reprocessing_repo=reprocessing_repo,
            event=event,
            correlation_id=correlation_id,
        )

    async def _upsert_reprocessing_state(
        self,
        *,
        reprocessing_repo: InstrumentReprocessingStateRepository,
        event: MarketPricePersistedEvent,
        correlation_id: str,
    ) -> None:
        await reprocessing_repo.upsert_state(
            security_id=event.security_id,
            price_date=event.price_date,
            correlation_id=correlation_id,
        )
