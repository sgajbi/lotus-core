"""Prove portfolio aggregation job recovery and concurrent claim behavior."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobLease,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_aggregation_repository,
)

PortfolioAggregationRepository = portfolio_aggregation_repository.PortfolioAggregationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_stale_aggregation_job_data(db_engine, clean_db):
    """Seed expired, current, and pending aggregation lease states."""

    with Session(db_engine) as session:
        now = datetime.now(UTC)
        expired_at = now - timedelta(minutes=20)
        current_expiry = now + timedelta(minutes=5)

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

        jobs = [
            PortfolioAggregationJob(
                portfolio_id="P1_STALE",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
                attempt_count=1,
                lease_owner="expired-worker",
                lease_token="expired-token",
                lease_expires_at=expired_at,
            ),
            PortfolioAggregationJob(
                portfolio_id="P2_RECENT",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
                attempt_count=1,
                lease_owner="current-worker",
                lease_token="current-token",
                lease_expires_at=current_expiry,
            ),
            PortfolioAggregationJob(
                portfolio_id="P3_PENDING",
                aggregation_date=date(2025, 8, 1),
                status="PENDING",
            ),
        ]
        session.add_all(jobs)
        session.commit()


async def test_recover_expired_job_leases_requeues_retryable_claim(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Requeue only an expired processing lease below its retry ceiling."""

    repo = PortfolioAggregationRepository(async_db_session)
    await async_db_session.execute(
        update(PortfolioAggregationJob)
        .where(PortfolioAggregationJob.portfolio_id == "P1_STALE")
        .values(failure_reason=portfolio_aggregation_repository.AGGREGATION_REPROCESS_REQUESTED)
    )
    await async_db_session.commit()

    recovery = await repo.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=3,
    )
    await async_db_session.commit()

    assert recovery.requeued_count == 1
    assert recovery.failed_count == 0

    with Session(db_engine) as session:
        job1 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P1_STALE").one()
        assert job1.status == "PENDING"
        assert job1.lease_owner is None
        assert job1.lease_token is None
        assert job1.lease_expires_at is None
        assert job1.failure_reason is None

        job2 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P2_RECENT").one()
        assert job2.status == "PROCESSING"
        assert job2.lease_token == "current-token"

        job3 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P3_PENDING").one()
        assert job3.status == "PENDING"


async def test_recover_expired_job_leases_fails_retry_exhausted_claim(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Fail an expired processing lease that reached its retry ceiling."""

    repo = PortfolioAggregationRepository(async_db_session)

    recovery = await repo.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=1,
    )
    await async_db_session.commit()

    assert recovery.requeued_count == 0
    assert recovery.failed_count == 1

    with Session(db_engine) as session:
        job1 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P1_STALE").one()
        assert job1.status == "FAILED"
        assert job1.failure_reason == "Aggregation job lease expired after max attempts"
        assert job1.lease_owner is None
        assert job1.lease_token is None
        assert job1.lease_expires_at is None


async def test_recover_expired_job_leases_does_not_overwrite_completed_rows(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Do not overwrite a terminal state won by a concurrent worker."""

    job_id = (
        (
            await async_db_session.execute(
                select(PortfolioAggregationJob.id).where(
                    PortfolioAggregationJob.portfolio_id == "P1_STALE"
                )
            )
        )
        .scalars()
        .one()
    )

    repo = PortfolioAggregationRepository(async_db_session)
    original_execute = async_db_session.execute
    execute_count = 0

    async def execute_with_concurrent_completion(*args, **kwargs):
        nonlocal execute_count
        execute_count += 1
        if execute_count == 2:
            with Session(db_engine) as session:
                session.execute(
                    update(PortfolioAggregationJob)
                    .where(PortfolioAggregationJob.id == job_id)
                    .values(status="COMPLETE", updated_at=datetime.now(UTC))
                )
                session.commit()
        return await original_execute(*args, **kwargs)

    async_db_session.execute = execute_with_concurrent_completion
    recovery = await repo.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=3,
    )
    await async_db_session.commit()

    assert recovery.requeued_count == 0
    assert recovery.failed_count == 0

    with Session(db_engine) as session:
        job = session.query(PortfolioAggregationJob).filter_by(id=job_id).one()
        assert job.status == "COMPLETE"


async def test_claim_eligible_jobs_does_not_double_claim_under_concurrency(
    clean_db, async_db_session: AsyncSession
):
    """Lease one ready job to only one of two concurrent claimers."""

    async_db_session.add(
        Portfolio(
            portfolio_id="P-AGG-CLAIM",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        Instrument(
            security_id="SEC-AGG-CLAIM",
            name="Aggregation Claim Instrument",
            isin="US-AGG-CLAIM",
            asset_class="EQUITY",
            product_type="COMMON_STOCK",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add(
        PortfolioAggregationJob(
            portfolio_id="P-AGG-CLAIM",
            aggregation_date=date(2025, 8, 15),
            status="PENDING",
        )
    )
    async_db_session.add(
        DailyPositionSnapshot(
            portfolio_id="P-AGG-CLAIM",
            security_id="SEC-AGG-CLAIM",
            date=date(2025, 8, 15),
            epoch=0,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            cost_basis_local=Decimal("1"),
            valuation_status="VALUED_CURRENT",
        )
    )
    async_db_session.add(
        PositionTimeseries(
            portfolio_id="P-AGG-CLAIM",
            security_id="SEC-AGG-CLAIM",
            date=date(2025, 8, 15),
            epoch=0,
            bod_market_value=Decimal("1"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("1"),
            fees=Decimal("0"),
            quantity=Decimal("1"),
            cost=Decimal("1"),
        )
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def claim_one(claimant: str):
        async with session_factory() as session:
            repo = PortfolioAggregationRepository(session)
            claimed = await repo.claim_eligible_jobs(
                batch_size=1,
                lease=AggregationJobLease(
                    owner=f"aggregation-runtime-{claimant}",
                    token=f"lease-token-{claimant}",
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                ),
            )
            await session.commit()
            return claimed

    first_claim, second_claim = await asyncio.gather(claim_one("one"), claim_one("two"))
    all_claimed = [*first_claim, *second_claim]

    assert len(all_claimed) == 1
    assert len({job.id for job in all_claimed}) == 1

    async with session_factory() as verification_session:
        jobs = (
            (
                await verification_session.execute(
                    select(PortfolioAggregationJob).where(
                        PortfolioAggregationJob.portfolio_id == "P-AGG-CLAIM",
                        PortfolioAggregationJob.aggregation_date == date(2025, 8, 15),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(jobs) == 1
    assert jobs[0].status == "PROCESSING"
    assert jobs[0].attempt_count == 1
    assert jobs[0].lease_token in {"lease-token-one", "lease-token-two"}
