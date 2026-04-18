import json
import logging
from datetime import date
from typing import Final

from confluent_kafka import Message
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from portfolio_common.db import get_async_db_session
from portfolio_common.events import (
    DailyPositionSnapshotPersistedEvent,
)
from portfolio_common.kafka_consumer import BaseConsumer
from pydantic import ValidationError
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from tenacity import before_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from ..core.position_timeseries_logic import PositionTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

MAX_DEPENDENT_PROPAGATION_ROWS = 500
_UNSET_PRELOAD: Final = object()


class PositionTimeseriesConsumer(BaseConsumer):
    async def process_message(self, msg: Message):
        retry_config = retry(
            wait=wait_fixed(3),
            stop=stop_after_attempt(15),
            before=before_log(logger, logging.INFO),
            retry=retry_if_exception_type(IntegrityError),
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
    def _material_state(timeseries_record) -> tuple[object, ...]:
        return (
            timeseries_record.bod_market_value,
            timeseries_record.bod_cashflow_position,
            timeseries_record.eod_cashflow_position,
            timeseries_record.bod_cashflow_portfolio,
            timeseries_record.eod_cashflow_portfolio,
            timeseries_record.eod_market_value,
            timeseries_record.fees,
            timeseries_record.quantity,
            timeseries_record.cost,
        )

    @classmethod
    def _has_material_change(cls, existing_record, new_record) -> bool:
        if existing_record is None:
            return True
        return cls._material_state(existing_record) != cls._material_state(new_record)

    async def _stage_aggregation_job(
        self, db_session, portfolio_id: str, a_date: date, correlation_id: str
    ):
        await self._stage_aggregation_jobs(db_session, portfolio_id, [a_date], correlation_id)

    async def _stage_aggregation_jobs(
        self, db_session, portfolio_id: str, aggregation_dates: list[date], correlation_id: str
    ) -> None:
        """
        Idempotently stage aggregation jobs.

        Material position-timeseries changes for a portfolio-day must re-arm aggregation,
        even when they arrive under the same correlation id as an earlier partial run.
        Duplicate timeseries writes are filtered before this method is called.
        """
        normalized_dates = sorted(set(aggregation_dates))
        if not normalized_dates:
            return

        job_stmt = (
            pg_insert(PortfolioAggregationJob)
            .values(
                [
                    {
                        "portfolio_id": portfolio_id,
                        "aggregation_date": aggregation_date,
                        "status": "PENDING",
                        "correlation_id": correlation_id,
                    }
                    for aggregation_date in normalized_dates
                ]
            )
            .on_conflict_do_update(
                index_elements=["portfolio_id", "aggregation_date"],
                set_={
                    "status": "PENDING",
                    "correlation_id": correlation_id,
                    "updated_at": func.now(),
                },
                where=or_(
                    PortfolioAggregationJob.status != "PENDING",
                    func.coalesce(PortfolioAggregationJob.correlation_id, "")
                    != (correlation_id or ""),
                ),
            )
        )
        await db_session.execute(job_stmt)
        logger.info(
            "Successfully staged %s aggregation job(s) for portfolio %s from %s to %s",
            len(normalized_dates),
            portfolio_id,
            normalized_dates[0],
            normalized_dates[-1],
        )

    async def _materialize_position_timeseries(
        self,
        repo: TimeseriesRepository,
        *,
        current_snapshot: DailyPositionSnapshot,
        previous_snapshot: DailyPositionSnapshot | None,
        epoch: int,
        require_existing: bool = False,
        existing_timeseries: PositionTimeseries | None | object = _UNSET_PRELOAD,
        cashflows: list[Cashflow] | object = _UNSET_PRELOAD,
    ) -> tuple[bool, object]:
        if existing_timeseries is _UNSET_PRELOAD:
            existing_timeseries = await repo.get_position_timeseries(
                current_snapshot.portfolio_id,
                current_snapshot.security_id,
                current_snapshot.date,
                epoch,
            )
        if require_existing and existing_timeseries is None:
            return False, None
        if cashflows is _UNSET_PRELOAD:
            cashflows = await repo.get_all_cashflows_for_security_date(
                current_snapshot.portfolio_id,
                current_snapshot.security_id,
                current_snapshot.date,
                epoch,
            )

        new_timeseries_record = PositionTimeseriesLogic.calculate_daily_record(
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            cashflows=cashflows,
            epoch=epoch,
        )
        if not self._has_material_change(existing_timeseries, new_timeseries_record):
            return False, new_timeseries_record

        await repo.upsert_position_timeseries(new_timeseries_record)
        return True, new_timeseries_record

    async def _propagate_dependent_position_timeseries(
        self,
        db_session,
        repo: TimeseriesRepository,
        *,
        current_snapshot: DailyPositionSnapshot,
        epoch: int,
        correlation_id: str,
    ) -> None:
        previous_snapshot = current_snapshot
        next_snapshots = await repo.get_next_snapshots_after(
            previous_snapshot.portfolio_id,
            previous_snapshot.security_id,
            previous_snapshot.date,
            epoch,
            MAX_DEPENDENT_PROPAGATION_ROWS,
        )
        if not next_snapshots:
            return

        next_dates = [snapshot.date for snapshot in next_snapshots]
        existing_timeseries_by_date = await repo.get_position_timeseries_for_dates(
            previous_snapshot.portfolio_id,
            previous_snapshot.security_id,
            next_dates,
            epoch,
        )
        cashflows_by_date = await repo.get_cashflows_for_security_dates(
            previous_snapshot.portfolio_id,
            previous_snapshot.security_id,
            next_dates,
            epoch,
        )
        changed_dates: list[date] = []
        for next_snapshot in next_snapshots:

            changed, _ = await self._materialize_position_timeseries(
                repo,
                current_snapshot=next_snapshot,
                previous_snapshot=previous_snapshot,
                epoch=epoch,
                require_existing=True,
                existing_timeseries=existing_timeseries_by_date.get(next_snapshot.date),
                cashflows=cashflows_by_date.get(next_snapshot.date, []),
            )
            if not changed:
                break

            changed_dates.append(next_snapshot.date)
            previous_snapshot = next_snapshot

        await self._stage_aggregation_jobs(
            db_session,
            current_snapshot.portfolio_id,
            changed_dates,
            correlation_id,
        )

        if len(next_snapshots) == MAX_DEPENDENT_PROPAGATION_ROWS:
            logger.warning(
                "Stopped dependent position-timeseries propagation after %s rows for %s/%s.",
                MAX_DEPENDENT_PROPAGATION_ROWS,
                current_snapshot.portfolio_id,
                current_snapshot.security_id,
            )

    async def _process_message_with_retry(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode("utf-8"))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = DailyPositionSnapshotPersistedEvent.model_validate(event_data)

                logger.info(
                    "Processing position snapshot for %s on %s for epoch %s",
                    event.security_id,
                    event.date,
                    event.epoch,
                )

                async for db in get_async_db_session():
                    async with db.begin():
                        repo = TimeseriesRepository(db)
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

                        changed, _ = await self._materialize_position_timeseries(
                            repo,
                            current_snapshot=current_snapshot,
                            previous_snapshot=previous_snapshot,
                            epoch=event.epoch,
                        )

                        if not changed:
                            logger.info(
                                (
                                    "Position timeseries already up to date for %s on %s epoch %s. "
                                    "Checking dependent rows before skipping downstream fan-out."
                                ),
                                event.security_id,
                                event.date,
                                event.epoch,
                            )
                        else:
                            await self._stage_aggregation_job(
                                db, event.portfolio_id, event.date, correlation_id
                            )
                        await self._propagate_dependent_position_timeseries(
                            db,
                            repo,
                            current_snapshot=current_snapshot,
                            epoch=event.epoch,
                            correlation_id=correlation_id,
                        )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed: %s. Sending to DLQ.", e, exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except IntegrityError as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)
