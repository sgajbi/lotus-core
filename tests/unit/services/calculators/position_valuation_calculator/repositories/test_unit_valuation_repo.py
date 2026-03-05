# tests/unit/services/calculators/position-valuation-calculator/repositories/test_valuation_repository.py  # noqa: E501
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    MarketPrice,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]


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
    Sets up position history for testing the holding lookup.
    - P1 holds S1 on the target date.
    - P2 sold S1 before the target date.
    - P3 holds S1, but the last history record is after the target date.
    - P4 holds a different security, S2.
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


async def test_find_portfolios_holding_security_on_date(
    db_engine, clean_db, setup_holdings_data, async_db_session: AsyncSession
):
    repo = ValuationRepository(async_db_session)
    target_date = date(2025, 8, 10)
    target_security = "S1"
    portfolio_ids = await repo.find_portfolios_holding_security_on_date(
        target_security, target_date
    )
    assert len(portfolio_ids) == 1
    assert portfolio_ids[0] == "P1"
