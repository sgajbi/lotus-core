# src/services/portfolio_aggregation_service/app/consumers/portfolio_timeseries_consumer.py
import json
import logging
from datetime import date
from typing import Optional

from confluent_kafka import Message
from portfolio_common.config import KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC
from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.db import get_async_db_session
from portfolio_common.events import (
    PortfolioAggregationDayCompletedEvent,
    PortfolioAggregationRequiredEvent,
)
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import ValidationError
from sqlalchemy import func, update

from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)


class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes scheduled aggregation jobs, calculates the daily portfolio time series
    record for the correct epoch, and updates the job status upon completion.
    """

    async def process_message(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode("utf-8"))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioAggregationRequiredEvent.model_validate(event_data)

                work_key = (event.portfolio_id, event.aggregation_date)
                logger.info(f"Received aggregation job for {work_key}.")

                await self._perform_aggregation(
                    portfolio_id=event.portfolio_id,
                    a_date=event.aggregation_date,
                    correlation_id=correlation_id,
                )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Message validation for aggregation job failed: %s. Sending to DLQ.",
                e,
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(
                "Unexpected error processing aggregation job for %s: %s",
                msg.key(),
                e,
                exc_info=True,
            )
            event = locals().get("event")
            if event:
                await self._update_job_status(event.portfolio_id, event.aggregation_date, "FAILED")
            await self._send_to_dlq_async(msg, e)

    async def _perform_aggregation(
        self, portfolio_id: str, a_date: date, correlation_id: Optional[str]
    ):
        try:
            async for db in get_async_db_session():
                async with db.begin():
                    repo = TimeseriesRepository(db)

                    portfolio = await repo.get_portfolio(portfolio_id)
                    if not portfolio:
                        raise ValueError(f"Portfolio {portfolio_id} not found during aggregation.")

                    # Determine the correct epoch to aggregate for this portfolio
                    target_epoch = await repo.get_current_epoch_for_portfolio(portfolio_id)

                    position_timeseries_list = await repo.get_all_position_timeseries_for_date(
                        portfolio_id, a_date, target_epoch
                    )

                    new_portfolio_record = await PortfolioTimeseriesLogic.calculate_daily_record(
                        portfolio=portfolio,
                        a_date=a_date,
                        epoch=target_epoch,
                        position_timeseries_list=position_timeseries_list,
                        repo=repo,
                    )

                    claimed_terminal = await self._update_job_status(
                        portfolio_id,
                        a_date,
                        "COMPLETE",
                        db_session=db,
                    )
                    if not claimed_terminal:
                        logger.warning(
                            "Skipping aggregation completion side effects after losing "
                            "job ownership.",
                            extra={"portfolio_id": portfolio_id, "aggregation_date": str(a_date)},
                        )
                        return

                    await repo.upsert_portfolio_timeseries(new_portfolio_record)
                    outbox_repo = OutboxRepository(db)

                    completion_event = PortfolioAggregationDayCompletedEvent(
                        portfolio_id=portfolio_id,
                        aggregation_date=a_date,
                        epoch=target_epoch,
                        correlation_id=correlation_id,
                    )
                    await outbox_repo.create_outbox_event(
                        aggregate_type="PortfolioAggregationStage",
                        aggregate_id=f"{portfolio_id}:{a_date}:{target_epoch}",
                        event_type="PortfolioAggregationDayCompleted",
                        topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
                        payload=completion_event.model_dump(mode="json"),
                        correlation_id=correlation_id,
                    )

            logger.info(
                "Aggregation job for (%s, %s) transactionally completed.",
                portfolio_id,
                a_date,
            )

        except Exception:
            logger.error(
                "Aggregation failed for (%s, %s). Marking job as FAILED.",
                portfolio_id,
                a_date,
                exc_info=True,
            )
            await self._update_job_status(portfolio_id, a_date, "FAILED")

    async def _update_job_status(
        self, portfolio_id: str, a_date: date, status: str, db_session=None
    ) -> bool:
        update_stmt = (
            update(PortfolioAggregationJob)
            .where(
                PortfolioAggregationJob.portfolio_id == portfolio_id,
                PortfolioAggregationJob.aggregation_date == a_date,
                PortfolioAggregationJob.status == "PROCESSING",
            )
            .values(status=status, updated_at=func.now())
        )

        if db_session:
            result = await db_session.execute(update_stmt)
            return result.rowcount == 1

        async for db in get_async_db_session():
            async with db.begin():
                result = await db.execute(update_stmt)
                return result.rowcount == 1
        return False
