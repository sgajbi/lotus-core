# tests/integration/services/query_service/test_cashflow_repository.py
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from portfolio_common.database_models import (
    Cashflow,
    Portfolio,
    PositionState,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

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


async def test_get_external_flows_uses_latest_cashflow_epoch(clean_db, async_db_session):
    """
    GIVEN a replayed external cashflow persisted in multiple epochs
    WHEN get_external_flows is called
    THEN it should return only the latest cashflow version for the transaction.
    """
    portfolio_id = "MWR_EPOCH_FILTER_PORT_01"
    transaction_id = "EXT_FLOW_TXN_01"

    async_db_session.add(
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
    async_db_session.add(
        Transaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="I-EXT-1",
            security_id="CASH_USD",
            transaction_date=date(2025, 1, 15),
            transaction_type="DEPOSIT",
            quantity=1,
            price=1,
            gross_transaction_amount=100,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 1, 15),
                amount=Decimal("100"),
                currency="USD",
                classification="CASHFLOW_IN",
                timing="BOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 1, 15),
                amount=Decimal("100"),
                currency="USD",
                classification="CASHFLOW_IN",
                timing="BOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=2,
            ),
        ]
    )
    await async_db_session.commit()

    repo = CashflowRepository(async_db_session)
    results = await repo.get_external_flows(portfolio_id, date(2025, 1, 1), date(2025, 1, 31))

    assert results == [(date(2025, 1, 15), Decimal("100"))]


async def test_get_portfolio_cashflow_series_uses_latest_cashflow_epoch(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN replayed portfolio-flow cashflows for the same transaction
    WHEN get_portfolio_cashflow_series is called
    THEN the daily total should reflect only the latest transaction epoch.
    """
    portfolio_id = "PORT_CF_SERIES_EPOCH_01"
    transaction_id = "PORT_CF_SERIES_TXN_01"

    async_db_session.add(
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
    async_db_session.add(
        Transaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="I-SER-1",
            security_id="CASH_USD",
            transaction_date=date(2025, 2, 1),
            transaction_type="WITHDRAWAL",
            quantity=1,
            price=1,
            gross_transaction_amount=50,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 2, 1),
                amount=Decimal("-50"),
                currency="USD",
                classification="CASHFLOW_OUT",
                timing="EOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 2, 1),
                amount=Decimal("-50"),
                currency="USD",
                classification="CASHFLOW_OUT",
                timing="EOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=4,
            ),
        ]
    )
    await async_db_session.commit()

    repo = CashflowRepository(async_db_session)
    results = await repo.get_portfolio_cashflow_series(
        portfolio_id, date(2025, 2, 1), date(2025, 2, 1)
    )

    assert results == [(date(2025, 2, 1), Decimal("-50"))]


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


async def test_cashflows_allow_same_transaction_id_across_epochs(clean_db, async_db_session):
    """
    GIVEN a transaction that is recalculated into a new epoch
    WHEN cashflows are persisted for both the original and replay epochs
    THEN the database should retain both versions keyed by (transaction_id, epoch).
    """
    portfolio_id = "EPOCH_CASHFLOW_PORT"
    security_id = "EPOCH_CASHFLOW_SEC"
    transaction_id = "EPOCH_CASHFLOW_TXN_01"

    async_db_session.add(
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
    async_db_session.add(
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id="I-EPOCH-1",
                security_id=security_id,
                transaction_date=date(2025, 2, 10),
                transaction_type="BUY",
                quantity=1,
                price=100,
                gross_transaction_amount=100,
                trade_currency="USD",
                currency="USD",
            )
        )
    async_db_session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=1,
                watermark_date=date(2025, 2, 9),
            )
        )
    await async_db_session.flush()

    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                cashflow_date=date(2025, 2, 10),
                amount=Decimal("-100"),
                currency="USD",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                calculation_type="NET",
                is_position_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                cashflow_date=date(2025, 2, 10),
                amount=Decimal("-100"),
                currency="USD",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                calculation_type="NET",
                is_position_flow=True,
                epoch=1,
            ),
        ]
    )
    await async_db_session.commit()

    result = await async_db_session.execute(
        sa.text(
            """
            SELECT transaction_id, epoch
            FROM cashflows
            WHERE transaction_id = :transaction_id
            ORDER BY epoch
            """
        ),
        {"transaction_id": transaction_id},
    )
    rows = result.fetchall()

    assert rows == [(transaction_id, 0), (transaction_id, 1)]
