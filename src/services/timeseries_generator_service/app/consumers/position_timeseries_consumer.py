import json
import logging
from dataclasses import asdict, dataclass
from datetime import date

from confluent_kafka import Message
from portfolio_common.config import KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC
from portfolio_common.database_models import DailyPositionSnapshot, PortfolioAggregationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.events import (
    DailyPositionSnapshotPersistedEvent,
    PositionTimeseriesDayCompletedEvent,
    ValuationDayCompletedEvent,
)
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..core.position_timeseries_logic import PositionTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "timeseries-generator"


class InstrumentNotFoundError(Exception):
    pass


class PreviousTimeseriesNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class _TimeseriesMaterialState:
    bod_market_value: object
    bod_cashflow_position: object
    eod_cashflow_position: object
    bod_cashflow_portfolio: object
    eod_cashflow_portfolio: object
    eod_market_value: object
    fees: object
    quantity: object
    cost: object


class PositionTimeseriesConsumer(BaseConsumer):
    @staticmethod
    def _parse_supported_event(event_data: dict) -> DailyPositionSnapshotPersistedEvent:
        try:
            return DailyPositionSnapshotPersistedEvent.model_validate(event_data)
        except ValidationError:
            valuation_event = ValuationDayCompletedEvent.model_validate(event_data)
            return DailyPositionSnapshotPersistedEvent(
                id=valuation_event.daily_position_snapshot_id,
                portfolio_id=valuation_event.portfolio_id,
                security_id=valuation_event.security_id,
                date=valuation_event.valuation_date,
                epoch=valuation_event.epoch,
            )

    async def process_message(self, msg: Message):
        retry_config = retry(
            wait=wait_fixed(3),
            stop=stop_after_attempt(15),
            before=before_log(logger, logging.INFO),
            retry=retry_if_exception_type((IntegrityError, InstrumentNotFoundError)),
        )
        retryable_process = retry_config(self._process_message_with_retry)
        try:
            await retryable_process(msg)
        except Exception as e:
            logger.error(
                "Fatal error after all retries for message %s-%s-%s. Sending to DLQ.",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)

    @staticmethod
    def _material_state(timeseries_record) -> _TimeseriesMaterialState:
        return _TimeseriesMaterialState(
            bod_market_value=timeseries_record.bod_market_value,
            bod_cashflow_position=timeseries_record.bod_cashflow_position,
            eod_cashflow_position=timeseries_record.eod_cashflow_position,
            bod_cashflow_portfolio=timeseries_record.bod_cashflow_portfolio,
            eod_cashflow_portfolio=timeseries_record.eod_cashflow_portfolio,
            eod_market_value=timeseries_record.eod_market_value,
            fees=timeseries_record.fees,
            quantity=timeseries_record.quantity,
            cost=timeseries_record.cost,
        )

    @classmethod
    def _has_material_change(cls, existing_record, new_record) -> bool:
        if existing_record is None:
            return True
        return asdict(cls._material_state(existing_record)) != asdict(
            cls._material_state(new_record)
        )

    async def _stage_aggregation_job(
        self, db_session, portfolio_id: str, a_date: date, correlation_id: str
    ):
        """
        Idempotently stage an aggregation job.

        Material position-timeseries changes for a portfolio-day must re-arm aggregation,
        even when they arrive under the same correlation id as an earlier partial run.
        Duplicate timeseries writes are filtered before this method is called.
        """
        job_stmt = (
            pg_insert(PortfolioAggregationJob)
            .values(
                portfolio_id=portfolio_id,
                aggregation_date=a_date,
                status="PENDING",
                correlation_id=correlation_id,
            )
            .on_conflict_do_update(
                index_elements=["portfolio_id", "aggregation_date"],
                set_={
                    "status": "PENDING",
                    "correlation_id": correlation_id,
                    "updated_at": func.now(),
                },
            )
        )
        await db_session.execute(job_stmt)
        logger.info(
            "Successfully staged aggregation job for portfolio %s on %s",
            portfolio_id,
            a_date,
        )

    async def _process_message_with_retry(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode("utf-8"))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = self._parse_supported_event(event_data)

                logger.info(
                    "Processing position snapshot for %s on %s for epoch %s",
                    event.security_id,
                    event.date,
                    event.epoch,
                )

                async for db in get_async_db_session():
                    async with db.begin():
                        repo = TimeseriesRepository(db)
                        outbox_repo = OutboxRepository(db)

                        # --- REFACTORED: Use EpochFencer ---
                        fencer = EpochFencer(db, service_name=SERVICE_NAME)
                        if not await fencer.check(event):
                            return  # Acknowledge message without processing
                        # --- END REFACTOR ---

                        instrument = await repo.get_instrument(event.security_id)
                        if not instrument:
                            raise InstrumentNotFoundError(
                                f"Instrument '{event.security_id}' not found. Will retry."
                            )

                        current_snapshot = await db.get(DailyPositionSnapshot, event.id)
                        if not current_snapshot:
                            logger.warning(
                                "DailyPositionSnapshot record with id %s not found. Skipping.",
                                event.id,
                            )
                            return

                        previous_snapshot = await repo.get_last_snapshot_before(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            a_date=event.date,
                            epoch=event.epoch,
                        )

                        cashflows = await repo.get_all_cashflows_for_security_date(
                            event.portfolio_id, event.security_id, event.date
                        )

                        existing_timeseries = await repo.get_position_timeseries(
                            event.portfolio_id, event.security_id, event.date, event.epoch
                        )

                        new_timeseries_record = PositionTimeseriesLogic.calculate_daily_record(
                            current_snapshot=current_snapshot,
                            previous_snapshot=previous_snapshot,
                            cashflows=cashflows,
                            epoch=event.epoch,
                        )

                        if not self._has_material_change(
                            existing_timeseries, new_timeseries_record
                        ):
                            logger.info(
                                (
                                    "Position timeseries already up to date for %s on %s epoch %s. "
                                    "Skipping downstream fan-out."
                                ),
                                event.security_id,
                                event.date,
                                event.epoch,
                            )
                            return

                        await repo.upsert_position_timeseries(new_timeseries_record)
                        await self._stage_aggregation_job(
                            db, event.portfolio_id, event.date, correlation_id
                        )
                        position_completion_event = PositionTimeseriesDayCompletedEvent(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            timeseries_date=event.date,
                            epoch=event.epoch,
                            correlation_id=correlation_id,
                        )
                        await outbox_repo.create_outbox_event(
                            aggregate_type="PositionTimeseriesStage",
                            aggregate_id=(
                                f"{event.portfolio_id}:{event.security_id}:{event.date}:{event.epoch}"
                            ),
                            event_type="PositionTimeseriesDayCompleted",
                            topic=KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC,
                            payload=position_completion_event.model_dump(mode="json"),
                            correlation_id=correlation_id,
                        )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed: %s. Sending to DLQ.", e, exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (InstrumentNotFoundError, IntegrityError) as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)
