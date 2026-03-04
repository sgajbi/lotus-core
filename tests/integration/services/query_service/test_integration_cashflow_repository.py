# tests/integration/services/query_service/test_cashflow_repository.py
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import (
    Portfolio,
    Transaction,
    Cashflow,
    PositionState,
    Instrument,
)
from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_cashflow_data(db_engine, clean_db):
    """
    Seeds the database with a mix of internal and external cashflows for testing.
    """
    portfolio_id = "MWR_TEST_PORT_01"
    security_id_income = "INCOME_SEC_01"
    with Session(db_engine) as session:
        # Prerequisites
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add(
            Transaction(
                transaction_id="T1",
                portfolio_id=portfolio_id,
                instrument_id="I1",
                security_id="S1",
                transaction_date=date(2025, 1, 15),
                transaction_type="DEPOSIT",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T2",
                portfolio_id=portfolio_id,
                instrument_id="I2",
                security_id="S2",
                transaction_date=date(2025, 1, 20),
                transaction_type="BUY",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T3",
                portfolio_id=portfolio_id,
                instrument_id="I3",
                security_id="S3",
                transaction_date=date(2025, 1, 25),
                transaction_type="WITHDRAWAL",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T4",
                portfolio_id=portfolio_id,
                instrument_id="I4",
                security_id=security_id_income,
                transaction_date=date(2025, 1, 1),
                transaction_type="DIVIDEND",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T5",
                portfolio_id=portfolio_id,
                instrument_id="I5",
                security_id=security_id_income,
                transaction_date=date(2025, 1, 1),
                transaction_type="INTEREST",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )

        # Add PositionState records for epoch-aware filtering
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id_income,
                epoch=1,
                watermark_date=date(2025, 1, 1),
            )
        )

        session.flush()

        # Cashflows to test against
        session.add_all(
            [
                # External, should be included
                Cashflow(
                    transaction_id="T1",
                    portfolio_id=portfolio_id,
                    cashflow_date=date(2025, 1, 15),
                    amount=Decimal("10000"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_portfolio_flow=True,
                ),
                # Internal, should be excluded
                Cashflow(
                    transaction_id="T2",
                    portfolio_id=portfolio_id,
                    security_id="S2",
                    cashflow_date=date(2025, 1, 20),
                    amount=Decimal("-5000"),
                    currency="USD",
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    calculation_type="NET",
                    is_portfolio_flow=False,
                ),
                # External, should be included
                Cashflow(
                    transaction_id="T3",
                    portfolio_id=portfolio_id,
                    cashflow_date=date(2025, 1, 25),
                    amount=Decimal("-2000"),
                    currency="USD",
                    classification="CASHFLOW_OUT",
                    timing="EOD",
                    calculation_type="NET",
                    is_portfolio_flow=True,
                ),
                # Income in correct epoch
                Cashflow(
                    transaction_id="T4",
                    portfolio_id=portfolio_id,
                    security_id=security_id_income,
                    cashflow_date=date(2025, 2, 1),
                    amount=Decimal("100"),
                    currency="USD",
                    classification="INCOME",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=True,
                    epoch=1,
                ),
                # Income in incorrect epoch (should be filtered out)
                Cashflow(
                    transaction_id="T5",
                    portfolio_id=portfolio_id,
                    security_id=security_id_income,
                    cashflow_date=date(2025, 2, 2),
                    amount=Decimal("999"),
                    currency="USD",
                    classification="INCOME",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=True,
                    epoch=0,
                ),
            ]
        )
        session.commit()


async def test_get_external_flows(setup_cashflow_data, async_db_session: AsyncSession):
    """
    GIVEN a mix of internal and external cashflows in the database
    WHEN get_external_flows is called
    THEN it should return only the two external flows (CASHFLOW_IN and CASHFLOW_OUT).
    """
    # ARRANGE
    repo = CashflowRepository(async_db_session)
    portfolio_id = "MWR_TEST_PORT_01"
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 31)

    # ACT
    results = await repo.get_external_flows(portfolio_id, start_date, end_date)

    # ASSERT
    assert len(results) == 2

    # Results are tuples of (date, amount)
    assert results[0][0] == date(2025, 1, 15)
    assert results[0][1] == Decimal("10000")

    assert results[1][0] == date(2025, 1, 25)
    assert results[1][1] == Decimal("-2000")


async def test_get_income_cashflows_is_epoch_aware(
    setup_cashflow_data, async_db_session: AsyncSession
):
    """
    GIVEN income cashflows in different epochs
    WHEN get_income_cashflows_for_position is called
    THEN it should only return the cashflow from the current, active epoch.
    """
    # ARRANGE
    repo = CashflowRepository(async_db_session)
    portfolio_id = "MWR_TEST_PORT_01"
    security_id = "INCOME_SEC_01"
    start_date = date(2025, 1, 1)
    end_date = date(2025, 3, 31)

    # ACT
    results = await repo.get_income_cashflows_for_position(
        portfolio_id, security_id, start_date, end_date
    )

    # ASSERT
    assert len(results) == 1
    # Verify it returned the record from epoch 1 and filtered out the one from epoch 0
    assert results[0].epoch == 1
    assert results[0].amount == Decimal("100")

