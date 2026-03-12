# tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py
from datetime import date, datetime, timedelta, timezone

import pytest
from portfolio_common.database_models import Portfolio, PortfolioAggregationJob
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_stale_aggregation_job_data(db_engine, clean_db):
    """
    Sets up a variety of aggregation jobs in the database:
    - One stale 'PROCESSING' job (should be reset).
    - One recent 'PROCESSING' job (should not be reset).
    - One stale 'PENDING' job (should not be reset).
    """
    with Session(db_engine) as session:
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=20)

        # --- THIS IS THE FIX ---
        # Create the prerequisite portfolio records first to satisfy the foreign key constraint.
        portfolios = [
            Portfolio(
                portfolio_id="P1_STALE",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
            Portfolio(
                portfolio_id="P2_RECENT",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
            Portfolio(
                portfolio_id="P3_PENDING",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
        ]
        session.add_all(portfolios)
        session.flush()
        # --- END FIX ---

        jobs = [
            # 1. Stale and PROCESSING -> Should be reset to PENDING
            PortfolioAggregationJob(
                portfolio_id="P1_STALE",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
            ),
            # 2. Recent and PROCESSING -> Should NOT be touched
            PortfolioAggregationJob(
                portfolio_id="P2_RECENT",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
            ),
            # 3. Stale and PENDING -> Should NOT be touched
            PortfolioAggregationJob(
                portfolio_id="P3_PENDING",
                aggregation_date=date(2025, 8, 1),
                status="PENDING",
            ),
        ]
        session.add_all(jobs)
        session.flush()

        # Force deterministic staleness at the database layer instead of relying on
        # ORM constructor-time timestamp persistence across dialect/runtime differences.
        session.execute(
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.portfolio_id == "P1_STALE")
            .values(updated_at=stale_time)
        )
        session.execute(
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.portfolio_id == "P2_RECENT")
            .values(updated_at=now)
        )
        session.execute(
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.portfolio_id == "P3_PENDING")
            .values(updated_at=stale_time)
        )
        session.commit()


async def test_find_and_reset_stale_aggregation_jobs(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """
    GIVEN a mix of recent and stale aggregation jobs
    WHEN find_and_reset_stale_jobs is called
    THEN it should only reset the single stale 'PROCESSING' job to 'PENDING'.
    """
    # ARRANGE
    repo = TimeseriesRepository(async_db_session)

    # ACT
    reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15)
    await async_db_session.commit()

    # ASSERT
    assert reset_count == 1

    with Session(db_engine) as session:
        # Verify the stale PROCESSING job was reset
        job1 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P1_STALE").one()
        assert job1.status == "PENDING"

        # Verify the other jobs were untouched
        job2 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P2_RECENT").one()
        assert job2.status == "PROCESSING"

        job3 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P3_PENDING").one()
        assert job3.status == "PENDING"
