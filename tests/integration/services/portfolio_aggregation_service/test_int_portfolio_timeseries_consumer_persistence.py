from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    OutboxEvent,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
)
from portfolio_common.events import PortfolioAggregationRequiredEvent
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_aggregation_service.app.consumers import (
    portfolio_timeseries_consumer as portfolio_timeseries_consumer_module,
)

pytestmark = pytest.mark.asyncio


async def test_aggregation_message_skips_side_effects_after_losing_job_ownership(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            Portfolio(
                portfolio_id="PORT-AGG-INT-01",
                base_currency="USD",
                open_date=date(2025, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="MEDIUM_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CLIENT-AGG-INT-01",
                is_leverage_allowed=False,
                status="ACTIVE",
            ),
            PortfolioAggregationJob(
                portfolio_id="PORT-AGG-INT-01",
                aggregation_date=date(2025, 8, 21),
                status="PROCESSING",
            ),
        ]
    )
    await async_db_session.commit()

    event = PortfolioAggregationRequiredEvent(
        portfolio_id="PORT-AGG-INT-01",
        aggregation_date=date(2025, 8, 21),
    )
    msg = MagicMock()
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    msg.key.return_value = event.portfolio_id.encode("utf-8")
    msg.headers.return_value = [("correlation_id", b"corr-agg-int-01")]

    consumer = portfolio_timeseries_consumer_module.PortfolioTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_day.aggregation.job.requested",
        group_id="test_group",
        dlq_topic="test.dlq",
    )
    consumer._send_to_dlq_async = AsyncMock()

    async def override_session():
        yield async_db_session

    async def complete_or_requeue_with_ownership_loss(
        self,
        portfolio_id,
        a_date,
        db_session=None,
    ):
        assert db_session is not None
        await db_session.execute(
            update(PortfolioAggregationJob)
            .where(
                PortfolioAggregationJob.portfolio_id == portfolio_id,
                PortfolioAggregationJob.aggregation_date == a_date,
            )
            .values(status="COMPLETE")
        )
        return "LOST_OWNERSHIP"

    deterministic_record = PortfolioTimeseries(
        portfolio_id="PORT-AGG-INT-01",
        date=date(2025, 8, 21),
        epoch=0,
        bod_market_value=Decimal("0"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("0"),
        eod_market_value=Decimal("0"),
        fees=Decimal("0"),
    )

    with (
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.get_async_db_session",
            new=override_session,
        ),
        patch.object(
            portfolio_timeseries_consumer_module.PortfolioTimeseriesConsumer,
            "_complete_or_requeue_job",
            new=complete_or_requeue_with_ownership_loss,
        ),
        patch(
            "src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer.PortfolioTimeseriesLogic.calculate_daily_record",
            new=AsyncMock(return_value=deterministic_record),
        ),
    ):
        await consumer.process_message(msg)

    portfolio_rows = (
        (
            await async_db_session.execute(
                select(PortfolioTimeseries).where(
                    PortfolioTimeseries.portfolio_id == "PORT-AGG-INT-01",
                    PortfolioTimeseries.date == date(2025, 8, 21),
                    PortfolioTimeseries.epoch == 0,
                )
            )
        )
        .scalars()
        .all()
    )
    outbox_rows = (
        (
            await async_db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == "PORT-AGG-INT-01:2025-08-21:0",
                    OutboxEvent.event_type == "PortfolioAggregationDayCompleted",
                )
            )
        )
        .scalars()
        .all()
    )
    job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == "PORT-AGG-INT-01",
            PortfolioAggregationJob.aggregation_date == date(2025, 8, 21),
        )
    )

    assert portfolio_rows == []
    assert outbox_rows == []
    assert job is not None
    assert job.status == "COMPLETE"
    consumer._send_to_dlq_async.assert_not_awaited()
