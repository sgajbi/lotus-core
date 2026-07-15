"""Kafka delivery and transitional orchestration for portfolio aggregation jobs."""

from __future__ import annotations

import json
import logging
from datetime import date

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import ValidationError

from ..application.stage_portfolio_aggregation_completion import (
    StagePortfolioAggregationCompletion,
)
from ..core.portfolio_timeseries_logic import PortfolioTimeseriesLogic
from ..domain.aggregation_records import (
    AggregationJobCompletionDisposition,
    PortfolioAggregationCompletion,
)
from ..infrastructure.aggregation_completion_event_stager import (
    TransactionalAggregationCompletionEventStager,
)
from ..infrastructure.portfolio_aggregation_repository import PortfolioAggregationRepository

logger = logging.getLogger(__name__)


class PortfolioTimeseriesConsumer(BaseConsumer):
    """
    Consumes scheduled aggregation jobs, calculates the daily portfolio time series
    record for the correct epoch, and updates the job status upon completion.
    """

    async def process_message(self, msg: Message) -> None:
        try:
            event_data = json.loads(_message_value(msg))
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=event_data.get("correlation_id"),
            ) as correlation_id:
                event = PortfolioAggregationRequiredEvent.model_validate(event_data)

                logger.info(
                    "Received aggregation job for (%s, %s).",
                    event.portfolio_id,
                    event.aggregation_date,
                )

                await self._perform_aggregation(
                    portfolio_id=event.portfolio_id,
                    a_date=event.aggregation_date,
                    correlation_id=correlation_id,
                )

        except (json.JSONDecodeError, ValidationError) as error:
            logger.error(
                "Message validation for aggregation job failed: %s. Sending to DLQ.",
                error,
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, error)
        except Exception as error:
            logger.error(
                "Unexpected error processing aggregation job for %s: %s",
                msg.key(),
                error,
                exc_info=True,
            )
            event = locals().get("event")
            if event:
                await self._mark_job_failed(event.portfolio_id, event.aggregation_date)
            await self._send_to_dlq_async(msg, error)

    async def _perform_aggregation(
        self,
        portfolio_id: str,
        a_date: date,
        correlation_id: str | None,
    ) -> None:
        try:
            async for db in get_async_db_session():
                async with db.begin():
                    repo = PortfolioAggregationRepository(db)

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

                    disposition = await repo.complete_or_requeue_job(portfolio_id, a_date)
                    if disposition is AggregationJobCompletionDisposition.REQUEUED:
                        logger.info(
                            "Requeued aggregation job after late material input.",
                            extra={"portfolio_id": portfolio_id, "aggregation_date": str(a_date)},
                        )
                        return
                    if disposition is not AggregationJobCompletionDisposition.COMPLETE:
                        logger.warning(
                            "Skipping aggregation completion side effects after losing "
                            "job ownership.",
                            extra={"portfolio_id": portfolio_id, "aggregation_date": str(a_date)},
                        )
                        return

                    await repo.upsert_portfolio_timeseries(new_portfolio_record)
                    outbox_repo = OutboxRepository(db)
                    await StagePortfolioAggregationCompletion(
                        event_stager=TransactionalAggregationCompletionEventStager(outbox_repo)
                    ).execute(
                        PortfolioAggregationCompletion(
                            portfolio_id=portfolio_id,
                            aggregation_date=a_date,
                            epoch=target_epoch,
                        ),
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
            await self._mark_job_failed(portfolio_id, a_date)

    async def _mark_job_failed(self, portfolio_id: str, a_date: date) -> bool:
        async for db in get_async_db_session():
            async with db.begin():
                return await PortfolioAggregationRepository(db).mark_job_failed(
                    portfolio_id,
                    a_date,
                )
        return False


def _message_value(msg: Message) -> str:
    value = msg.value()
    if value is None:
        raise ValueError("Portfolio aggregation job payload is missing")
    return value.decode("utf-8")
