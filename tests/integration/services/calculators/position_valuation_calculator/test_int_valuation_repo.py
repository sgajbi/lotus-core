# tests/integration/services/calculators/position-valuation-calculator/test_valuation_repository.py
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    MarketPrice,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    Transaction,
)
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_stale_job_data(db_engine):
    """
    Sets up a variety of valuation jobs in the database:
    - One recent 'PROCESSING' job (should not be reset).
    - One stale 'PROCESSING' job (should be reset).
    - One stale 'PENDING' job (should not be reset).
    - One stale 'COMPLETE' job (should not be reset).
    """
    with Session(db_engine) as session:
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=30)

        jobs = [
            PortfolioValuationJob(
                portfolio_id="P1",
                security_id="S1",
                valuation_date=date(2025, 8, 1),
                status="PROCESSING",
                updated_at=stale_time,
            ),
            PortfolioValuationJob(
                portfolio_id="P2",
                security_id="S2",
                valuation_date=date(2025, 8, 1),
                status="PROCESSING",
                updated_at=now,
            ),
            PortfolioValuationJob(
                portfolio_id="P3",
                security_id="S3",
                valuation_date=date(2025, 8, 1),
                status="PENDING",
                updated_at=stale_time,
            ),
            PortfolioValuationJob(
                portfolio_id="P4",
                security_id="S4",
                valuation_date=date(2025, 8, 1),
                status="COMPLETE",
                updated_at=stale_time,
            ),
        ]
        session.add_all(jobs)
        session.commit()


@pytest.fixture(scope="function")
def setup_holdings_data(db_engine):
    """
    Sets up position history for testing the holding lookup. This fixture
    populates the `position_history` table.
    """
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    portfolio_id="P1",
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
                    portfolio_id="P2",
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
                    portfolio_id="P3",
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
                    portfolio_id="P4",
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
        )
        session.add_all(
            [
                Transaction(
                    transaction_id="T1",
                    portfolio_id="P1",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=datetime.now(),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T2",
                    portfolio_id="P2",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=datetime.now(),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T3",
                    portfolio_id="P3",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=datetime.now(),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T4",
                    portfolio_id="P4",
                    instrument_id="I2",
                    security_id="S2",
                    transaction_date=datetime.now(),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionState(
                    portfolio_id="P1",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P2",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P3",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P4",
                    security_id="S2",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
            ]
        )

        history_records = [
            PositionHistory(
                transaction_id="T1",
                portfolio_id="P1",
                security_id="S1",
                position_date=date(2025, 8, 5),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            PositionHistory(
                transaction_id="T2",
                portfolio_id="P2",
                security_id="S1",
                position_date=date(2025, 8, 4),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            PositionHistory(
                transaction_id="T2",
                portfolio_id="P2",
                security_id="S1",
                position_date=date(2025, 8, 6),
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
            ),
            PositionHistory(
                transaction_id="T3",
                portfolio_id="P3",
                security_id="S1",
                position_date=date(2025, 8, 15),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            PositionHistory(
                transaction_id="T4",
                portfolio_id="P4",
                security_id="S2",
                position_date=date(2025, 8, 5),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
        ]
        session.add_all(history_records)
        session.commit()


@pytest.fixture(scope="function")
def setup_snapshot_data(db_engine):
    """
    Sets up position snapshots for testing snapshot-based lookups. This fixture
    populates the `daily_position_snapshots` table.
    """
    with Session(db_engine) as session:
        portfolios = [
            Portfolio(
                portfolio_id=f"P{i}",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id=f"e{i}",
                status="f",
            )
            for i in range(1, 5)
        ]
        session.add_all(portfolios)
        session.flush()

        snapshots = [
            DailyPositionSnapshot(
                portfolio_id="P1",
                security_id="S1",
                date=date(2025, 8, 5),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            DailyPositionSnapshot(
                portfolio_id="P2",
                security_id="S1",
                date=date(2025, 8, 4),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            DailyPositionSnapshot(
                portfolio_id="P2",
                security_id="S1",
                date=date(2025, 8, 6),
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
            ),
            DailyPositionSnapshot(
                portfolio_id="P3",
                security_id="S1",
                date=date(2025, 8, 15),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            DailyPositionSnapshot(
                portfolio_id="P4",
                security_id="S2",
                date=date(2025, 8, 5),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
        ]
        session.add_all(snapshots)
        session.commit()


@pytest.fixture(scope="function")
def setup_price_data(db_engine):
    """Sets up market prices for testing the next price lookup."""
    with Session(db_engine) as session:
        prices = [
            MarketPrice(
                security_id="S1", price_date=date(2025, 8, 1), price=Decimal("100"), currency="USD"
            ),
            MarketPrice(
                security_id="S1", price_date=date(2025, 8, 5), price=Decimal("105"), currency="USD"
            ),
            MarketPrice(
                security_id="S1", price_date=date(2025, 8, 10), price=Decimal("110"), currency="USD"
            ),
            MarketPrice(
                security_id="S2", price_date=date(2025, 8, 5), price=Decimal("200"), currency="USD"
            ),
        ]
        session.add_all(prices)
        session.commit()


@pytest.fixture(scope="function")
def setup_first_open_date_data(db_engine):
    """Sets up position history records for testing the first_open_date query."""
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    portfolio_id="P1",
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
                    portfolio_id="P2",
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
        )
        session.add_all(
            [
                Transaction(
                    transaction_id="T1",
                    portfolio_id="P1",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=date(2025, 1, 1),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T2",
                    portfolio_id="P1",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=date(2025, 1, 1),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T3",
                    portfolio_id="P1",
                    instrument_id="I2",
                    security_id="S2",
                    transaction_date=date(2025, 1, 1),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="T4",
                    portfolio_id="P2",
                    instrument_id="I1",
                    security_id="S1",
                    transaction_date=date(2025, 1, 1),
                    transaction_type="BUY",
                    quantity=1,
                    price=1,
                    gross_transaction_amount=1,
                    trade_currency="USD",
                    currency="USD",
                ),
            ]
        )
        session.commit()
        session.add_all(
            [
                PositionState(
                    portfolio_id="P1",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P1",
                    security_id="S2",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P2",
                    security_id="S1",
                    epoch=1,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionHistory(
                    transaction_id="T1",
                    portfolio_id="P1",
                    security_id="S1",
                    position_date=date(2025, 3, 15),
                    epoch=0,
                    quantity=1,
                    cost_basis=1,
                ),
                PositionHistory(
                    transaction_id="T2",
                    portfolio_id="P1",
                    security_id="S1",
                    position_date=date(2025, 4, 1),
                    epoch=0,
                    quantity=1,
                    cost_basis=1,
                ),
                PositionHistory(
                    transaction_id="T3",
                    portfolio_id="P1",
                    security_id="S2",
                    position_date=date(2025, 2, 10),
                    epoch=0,
                    quantity=1,
                    cost_basis=1,
                ),
                PositionHistory(
                    transaction_id="T4",
                    portfolio_id="P2",
                    security_id="S1",
                    position_date=date(2025, 5, 5),
                    epoch=0,
                    quantity=1,
                    cost_basis=1,
                ),
                PositionHistory(
                    transaction_id="T4",
                    portfolio_id="P2",
                    security_id="S1",
                    position_date=date(2025, 6, 6),
                    epoch=1,
                    quantity=1,
                    cost_basis=1,
                ),
            ]
        )
        session.commit()


@pytest_asyncio.fixture(scope="function")
async def session_factory(db_engine):
    """Provides a factory for creating new, isolated AsyncSessions for the test."""
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    async_engine = create_async_engine(async_url)
    factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await async_engine.dispose()


async def test_get_all_open_positions(
    db_engine, clean_db, setup_snapshot_data, async_db_session: AsyncSession
):
    """
    GIVEN a database with various positions, some open and some closed
    WHEN get_all_open_positions is called
    THEN it should return only the (portfolio_id, security_id) pairs with a non-zero quantity.
    """
    repo = ValuationRepository(async_db_session)
    open_positions = await repo.get_all_open_positions()

    assert len(open_positions) == 3
    position_set = {(p["portfolio_id"], p["security_id"]) for p in open_positions}
    assert ("P1", "S1") in position_set
    assert ("P3", "S1") in position_set
    assert ("P4", "S2") in position_set
    assert ("P2", "S1") not in position_set


async def test_get_next_price_date(
    db_engine, clean_db, setup_price_data, async_db_session: AsyncSession
):
    """
    GIVEN a series of market prices for a security
    WHEN get_next_price_date is called with a specific date
    THEN it should return the date of the very next price record.
    """
    repo = ValuationRepository(async_db_session)
    next_date = await repo.get_next_price_date(security_id="S1", after_date=date(2025, 8, 5))
    no_next_date = await repo.get_next_price_date(security_id="S1", after_date=date(2025, 8, 10))

    assert next_date == date(2025, 8, 10)
    assert no_next_date is None


async def test_find_portfolios_holding_security_on_date(
    db_engine, clean_db, setup_holdings_data, async_db_session: AsyncSession
):
    """
    GIVEN a set of portfolios with various position histories for security 'S1'
    WHEN find_portfolios_holding_security_on_date is called for 'S1' on a specific date
    THEN it should only return the portfolio that had a non-zero position on or before that date.
    """
    repo = ValuationRepository(async_db_session)
    target_date = date(2025, 8, 10)
    target_security = "S1"

    portfolio_ids = await repo.find_portfolios_holding_security_on_date(
        target_security, target_date
    )

    assert len(portfolio_ids) == 1
    assert portfolio_ids[0] == "P1"


async def test_find_open_position_keys_for_security_on_date_uses_current_epoch_only(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            portfolio_id="P-CURRENT-1",
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
    async_db_session.add_all(
        [
            Transaction(
                transaction_id="T-CURRENT-0",
                portfolio_id="P-CURRENT-1",
                instrument_id="I-CURRENT-1",
                security_id="S-CURRENT-1",
                transaction_date=datetime(2025, 8, 1, 9, 0, 0),
                transaction_type="BUY",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="T-CURRENT-1",
                portfolio_id="P-CURRENT-1",
                instrument_id="I-CURRENT-1",
                security_id="S-CURRENT-1",
                transaction_date=datetime(2025, 8, 2, 9, 0, 0),
                transaction_type="BUY",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            ),
            PositionState(
                portfolio_id="P-CURRENT-1",
                security_id="S-CURRENT-1",
                epoch=1,
                watermark_date=date(2025, 8, 2),
                status="CURRENT",
            ),
        ]
    )
    await async_db_session.commit()
    async_db_session.add_all(
        [
            PositionHistory(
                transaction_id="T-CURRENT-0",
                portfolio_id="P-CURRENT-1",
                security_id="S-CURRENT-1",
                position_date=date(2025, 8, 1),
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal("10"),
            ),
            PositionHistory(
                transaction_id="T-CURRENT-1",
                portfolio_id="P-CURRENT-1",
                security_id="S-CURRENT-1",
                position_date=date(2025, 8, 2),
                epoch=1,
                quantity=Decimal("12"),
                cost_basis=Decimal("12"),
            ),
        ]
    )
    await async_db_session.commit()

    repo = ValuationRepository(async_db_session)
    keys = await repo.find_open_position_keys_for_security_on_date("S-CURRENT-1", date(2025, 8, 2))

    assert keys == [("P-CURRENT-1", "S-CURRENT-1", 1)]


async def test_find_and_reset_stale_jobs(
    clean_db, setup_stale_job_data, session_factory: async_sessionmaker
):
    """
    GIVEN a mix of recent and stale jobs in various states
    WHEN find_and_reset_stale_jobs is called
    THEN it should only reset the single stale 'PROCESSING' job to 'PENDING'.
    """
    async with session_factory() as session:
        initial_states = {
            row.portfolio_id: row.status
            for row in (
                await session.execute(
                    select(PortfolioValuationJob).where(
                        PortfolioValuationJob.portfolio_id.in_(["P1", "P2", "P3", "P4"])
                    )
                )
            )
            .scalars()
            .all()
        }

    async with session_factory() as session:
        repo = ValuationRepository(session)
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)
        await session.commit()
    assert reset_count == 1

    async with session_factory() as session:
        job1 = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.portfolio_id == "P1")
            )
        ).scalar_one()
        assert job1.status == "PENDING"
        job2 = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.portfolio_id == "P2")
            )
        ).scalar_one()
        assert job2.status == initial_states["P2"]
        job3 = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.portfolio_id == "P3")
            )
        ).scalar_one()
        assert job3.status == initial_states["P3"]
        job4 = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.portfolio_id == "P4")
            )
        ).scalar_one()
        assert job4.status == initial_states["P4"]


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    clean_db, setup_stale_job_data, session_factory: async_sessionmaker
):
    async with session_factory() as session:
        repo = ValuationRepository(session)
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=0)
        await session.commit()

    assert reset_count == 0

    async with session_factory() as session:
        job1 = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.portfolio_id == "P1")
            )
        ).scalar_one()
        assert job1.status == "FAILED"
        assert job1.failure_reason == "Stale processing timeout exceeded max attempts"


async def test_find_and_reset_stale_jobs_does_not_overwrite_completed_rows(
    clean_db, setup_stale_job_data, session_factory: async_sessionmaker
):
    async with session_factory() as session:
        job_id = (
            (
                await session.execute(
                    select(PortfolioValuationJob.id).where(
                        PortfolioValuationJob.portfolio_id == "P1"
                    )
                )
            )
            .scalars()
            .one()
        )

    async with session_factory() as session:
        repo = ValuationRepository(session)
        original_execute = session.execute
        execute_count = 0

        async def execute_with_concurrent_completion(*args, **kwargs):
            nonlocal execute_count
            execute_count += 1
            if execute_count == 2:
                async with session_factory() as concurrent_session:
                    await concurrent_session.execute(
                        update(PortfolioValuationJob)
                        .where(PortfolioValuationJob.id == job_id)
                        .values(status="COMPLETE", updated_at=datetime.now(timezone.utc))
                    )
                    await concurrent_session.commit()
            return await original_execute(*args, **kwargs)

        session.execute = execute_with_concurrent_completion
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)
        await session.commit()

    assert reset_count == 0

    async with session_factory() as session:
        job = (
            await session.execute(
                select(PortfolioValuationJob).where(PortfolioValuationJob.id == job_id)
            )
        ).scalar_one()
        assert job.status == "COMPLETE"


async def test_get_first_open_dates_for_keys(
    clean_db, setup_first_open_date_data, async_db_session: AsyncSession
):
    """
    GIVEN a set of position history records for various keys and epochs
    WHEN get_first_open_dates_for_keys is called
    THEN it should return a dictionary mapping each key to its earliest position_date.
    """
    repo = ValuationRepository(async_db_session)
    keys_to_query = [("P1", "S1", 0), ("P1", "S2", 0), ("P2", "S1", 1), ("P99", "S99", 0)]

    first_open_dates = await repo.get_first_open_dates_for_keys(keys_to_query)

    assert len(first_open_dates) == 3
    assert first_open_dates[("P1", "S1", 0)] == date(2025, 3, 15)
    assert first_open_dates[("P1", "S2", 0)] == date(2025, 2, 10)
    assert first_open_dates[("P2", "S1", 1)] == date(2025, 6, 6)
    assert ("P99", "S99", 0) not in first_open_dates


async def test_stale_older_epoch_job_is_not_rearmed_when_newer_epoch_exists(
    async_db_session: AsyncSession, clean_db
):
    repo = ValuationJobRepository(async_db_session)

    await repo.upsert_job(
        portfolio_id="P-STAGE-1",
        security_id="S-STAGE-1",
        valuation_date=date(2025, 8, 11),
        epoch=3,
        correlation_id="corr-newer",
    )
    await async_db_session.commit()

    await repo.upsert_job(
        portfolio_id="P-STAGE-1",
        security_id="S-STAGE-1",
        valuation_date=date(2025, 8, 11),
        epoch=2,
        correlation_id="corr-stale",
    )
    await async_db_session.commit()

    jobs = (
        (
            await async_db_session.execute(
                select(PortfolioValuationJob).where(
                    PortfolioValuationJob.portfolio_id == "P-STAGE-1",
                    PortfolioValuationJob.security_id == "S-STAGE-1",
                    PortfolioValuationJob.valuation_date == date(2025, 8, 11),
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(jobs) == 1
    assert jobs[0].epoch == 3
    assert jobs[0].correlation_id == "corr-newer"


async def test_upsert_job_deduplicates_concurrent_duplicate_scheduler_pressure(
    async_db_session: AsyncSession, clean_db
):
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    barrier_lock = asyncio.Lock()
    barrier_ready = asyncio.Event()
    barrier_count = 0

    async def upsert_one() -> None:
        nonlocal barrier_count
        async with session_factory() as session:
            repo = ValuationJobRepository(session)
            original_get_latest_epoch = repo.get_latest_epoch_for_scope

            async def synchronized_get_latest_epoch_for_scope(**kwargs):
                nonlocal barrier_count
                result = await original_get_latest_epoch(**kwargs)
                async with barrier_lock:
                    barrier_count += 1
                    if barrier_count == 2:
                        barrier_ready.set()
                await barrier_ready.wait()
                return result

            repo.get_latest_epoch_for_scope = synchronized_get_latest_epoch_for_scope  # type: ignore[method-assign]
            await repo.upsert_job(
                portfolio_id="P-VAL-CONC",
                security_id="S-VAL-CONC",
                valuation_date=date(2025, 8, 14),
                epoch=4,
                correlation_id="corr-val-conc",
            )
            await session.commit()

    await asyncio.gather(upsert_one(), upsert_one())

    async with session_factory() as verification_session:
        jobs = (
            (
                await verification_session.execute(
                    select(PortfolioValuationJob).where(
                        PortfolioValuationJob.portfolio_id == "P-VAL-CONC",
                        PortfolioValuationJob.security_id == "S-VAL-CONC",
                        PortfolioValuationJob.valuation_date == date(2025, 8, 14),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(jobs) == 1
    assert jobs[0].epoch == 4
    assert jobs[0].status == "PENDING"
    assert jobs[0].correlation_id == "corr-val-conc"


async def test_get_latest_business_date_falls_back_to_processing_dates_when_calendar_is_empty(
    clean_db, async_db_session: AsyncSession
):
    repo = ValuationRepository(async_db_session)

    async_db_session.add(
        Portfolio(
            portfolio_id="P-FALLBACK-1",
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
    await async_db_session.commit()

    async_db_session.add_all(
        [
            PortfolioValuationJob(
                portfolio_id="P-FALLBACK-1",
                security_id="S-FALLBACK-1",
                valuation_date=date(2025, 8, 10),
                epoch=0,
                status="COMPLETE",
            ),
            DailyPositionSnapshot(
                portfolio_id="P-FALLBACK-1",
                security_id="S-FALLBACK-1",
                date=date(2025, 8, 5),
                quantity=Decimal("1"),
                cost_basis=Decimal("1"),
            ),
        ]
    )
    await async_db_session.commit()

    latest_date = await repo.get_latest_business_date()

    assert latest_date == date(2025, 8, 10)
