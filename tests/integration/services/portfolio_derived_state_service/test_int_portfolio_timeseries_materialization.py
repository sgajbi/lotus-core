"""Prove lease-fenced portfolio materialization against PostgreSQL."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import (
    OutboxEvent,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_derived_state_service.app.application.portfolio_timeseries import (
    MaterializePortfolioTimeseries,
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_timeseries_unit_of_work_provider as unit_of_work_provider_module,
)

pytestmark = pytest.mark.asyncio


async def test_stale_lease_cannot_persist_portfolio_output_or_completion_event(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    job = PortfolioAggregationJob(
        portfolio_id="PORT-AGG-INT-01",
        aggregation_date=date(2025, 8, 21),
        status="PROCESSING",
        lease_owner="aggregation-runtime-current",
        lease_token="current-lease-token",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
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
            job,
        ]
    )
    await async_db_session.commit()
    await async_db_session.refresh(job)

    async def override_session():
        yield async_db_session

    calculator = AsyncMock()
    calculator.calculate_daily_record.return_value = PortfolioTimeseries(
        portfolio_id="PORT-AGG-INT-01",
        date=date(2025, 8, 21),
        epoch=0,
        bod_market_value=Decimal("0"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("0"),
        eod_market_value=Decimal("0"),
        fees=Decimal("0"),
    )
    use_case = MaterializePortfolioTimeseries(
        unit_of_work_provider=(
            unit_of_work_provider_module.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()
        ),
        calculator=calculator,
    )

    with patch(
        "src.services.portfolio_derived_state_service.app.infrastructure."
        "portfolio_timeseries_unit_of_work_provider.get_async_db_session",
        new=override_session,
    ):
        result = await use_case.execute(
            MaterializePortfolioTimeseriesCommand(
                job_id=job.id,
                lease_token="expired-lease-token",
                portfolio_id=job.portfolio_id,
                aggregation_date=job.aggregation_date,
                correlation_id="corr-agg-int-01",
            )
        )

    portfolio_rows = (
        (
            await async_db_session.execute(
                select(PortfolioTimeseries).where(
                    PortfolioTimeseries.portfolio_id == job.portfolio_id,
                    PortfolioTimeseries.date == job.aggregation_date,
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
    await async_db_session.refresh(job)

    assert result.status is PortfolioTimeseriesMaterializationStatus.LOST_OWNERSHIP
    assert portfolio_rows == []
    assert outbox_rows == []
    assert job.status == "PROCESSING"
    assert job.lease_token == "current-lease-token"
