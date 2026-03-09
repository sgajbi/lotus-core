# tests/integration/services/calculators/position_calculator/test_int_position_calc_repo.py
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    Portfolio,
    PositionHistory,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# This now correctly imports the repository we want to test
from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_open_positions_data(db_engine):
    """
    Sets up a portfolio with multiple securities, where some positions are open and some are closed.
    """
    with Session(db_engine) as session:
        portfolio = Portfolio(
            portfolio_id="OPEN_POS_TEST_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
        session.add(portfolio)
        session.flush()

        snapshots = [
            # S1: Open position
            DailyPositionSnapshot(
                portfolio_id="OPEN_POS_TEST_01",
                security_id="S1_OPEN",
                date=date(2025, 8, 1),
                quantity=Decimal("100"),
                cost_basis=Decimal("1"),
            ),
            # S2: Closed position
            DailyPositionSnapshot(
                portfolio_id="OPEN_POS_TEST_01",
                security_id="S2_CLOSED",
                date=date(2025, 8, 2),
                quantity=Decimal("50"),
                cost_basis=Decimal("1"),
            ),
            DailyPositionSnapshot(
                portfolio_id="OPEN_POS_TEST_01",
                security_id="S2_CLOSED",
                date=date(2025, 8, 3),
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
            ),
            # S3: Open position, snapshot is old but it's the latest
            DailyPositionSnapshot(
                portfolio_id="OPEN_POS_TEST_01",
                security_id="S3_OPEN_OLD",
                date=date(2025, 7, 15),
                quantity=Decimal("200"),
                cost_basis=Decimal("1"),
            ),
        ]
        session.add_all(snapshots)
        session.commit()


# --- NEW FIXTURE ---
@pytest.fixture(scope="function")
def setup_snapshot_date_data(db_engine):
    """
    Sets up snapshots for a single key across different epochs to test the date lookup.
    """
    with Session(db_engine) as session:
        portfolio = Portfolio(
            portfolio_id="SNAP_DATE_TEST_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
        session.add(portfolio)
        session.flush()

        snapshots = [
            # Epoch 0 snapshots
            DailyPositionSnapshot(
                portfolio_id="SNAP_DATE_TEST_01",
                security_id="S1",
                date=date(2025, 8, 1),
                epoch=0,
                quantity=1,
                cost_basis=1,
            ),
            DailyPositionSnapshot(
                portfolio_id="SNAP_DATE_TEST_01",
                security_id="S1",
                date=date(2025, 8, 5),
                epoch=0,
                quantity=1,
                cost_basis=1,
            ),  # Max date for epoch 0
            # Epoch 1 snapshots
            DailyPositionSnapshot(
                portfolio_id="SNAP_DATE_TEST_01",
                security_id="S1",
                date=date(2025, 8, 10),
                epoch=1,
                quantity=1,
                cost_basis=1,
            ),  # Should be ignored for epoch 0 query
        ]
        session.add_all(snapshots)
        session.commit()


@pytest.fixture(scope="function")
def setup_position_history_date_data(db_engine):
    """
    Sets up position history for a single key across different epochs to test
    the latest position-history lookup used by back-dated trigger logic.
    """
    with Session(db_engine) as session:
        portfolio = Portfolio(
            portfolio_id="POS_HIST_DATE_TEST_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
        session.add(portfolio)
        session.flush()

        transactions = [
            Transaction(
                transaction_id="TXN_E0_A",
                portfolio_id="POS_HIST_DATE_TEST_01",
                instrument_id="I1",
                security_id="S1",
                transaction_date=date(2025, 8, 1),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TXN_E0_B",
                portfolio_id="POS_HIST_DATE_TEST_01",
                instrument_id="I1",
                security_id="S1",
                transaction_date=date(2025, 8, 6),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
            Transaction(
                transaction_id="TXN_E1_A",
                portfolio_id="POS_HIST_DATE_TEST_01",
                instrument_id="I1",
                security_id="S1",
                transaction_date=date(2025, 8, 9),
                transaction_type="BUY",
                quantity=Decimal("1"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("1"),
                trade_currency="USD",
                currency="USD",
            ),
        ]

        history_rows = [
            PositionHistory(
                portfolio_id="POS_HIST_DATE_TEST_01",
                security_id="S1",
                transaction_id="TXN_E0_A",
                position_date=date(2025, 8, 1),
                quantity=Decimal("1"),
                cost_basis=Decimal("1"),
                epoch=0,
            ),
            PositionHistory(
                portfolio_id="POS_HIST_DATE_TEST_01",
                security_id="S1",
                transaction_id="TXN_E0_B",
                position_date=date(2025, 8, 6),
                quantity=Decimal("2"),
                cost_basis=Decimal("2"),
                epoch=0,
            ),
            PositionHistory(
                portfolio_id="POS_HIST_DATE_TEST_01",
                security_id="S1",
                transaction_id="TXN_E1_A",
                position_date=date(2025, 8, 9),
                quantity=Decimal("3"),
                cost_basis=Decimal("3"),
                epoch=1,
            ),
        ]
        session.add_all(transactions)
        session.flush()
        session.add_all(history_rows)
        session.commit()


async def test_find_open_security_ids_as_of(
    clean_db, setup_open_positions_data, async_db_session: AsyncSession
):
    """
    GIVEN a portfolio with a mix of open and closed positions
    WHEN find_open_security_ids_as_of is called
    THEN it should return only the security IDs of the open positions.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "OPEN_POS_TEST_01"
    as_of_date = date(2025, 8, 5)

    # ACT
    open_security_ids = await repo.find_open_security_ids_as_of(portfolio_id, as_of_date)

    # ASSERT
    assert len(open_security_ids) == 2
    assert "S1_OPEN" in open_security_ids
    assert "S3_OPEN_OLD" in open_security_ids
    assert "S2_CLOSED" not in open_security_ids


async def test_get_latest_business_date(clean_db, db_engine, async_db_session: AsyncSession):
    """
    GIVEN several business dates in the database
    WHEN get_latest_business_date is called
    THEN it should return the most recent date.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    latest_date = date(2025, 8, 20)
    with Session(db_engine) as session:
        session.add_all(
            [
                BusinessDate(date=date(2025, 8, 18)),
                BusinessDate(date=latest_date),
                BusinessDate(date=date(2025, 8, 19)),
            ]
        )
        session.commit()

    # ACT
    result = await repo.get_latest_business_date()

    # ASSERT
    assert result == latest_date


# --- NEW TEST ---
async def test_get_latest_completed_snapshot_date(
    clean_db, setup_snapshot_date_data, async_db_session: AsyncSession
):
    """
    GIVEN snapshots exist for a key in different epochs
    WHEN get_latest_completed_snapshot_date is called for a specific epoch
    THEN it should return the max date for only that epoch.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "SNAP_DATE_TEST_01"
    security_id = "S1"

    # ACT
    # Query for epoch 0, which should return the latest date from that epoch's snapshots
    result_epoch_0 = await repo.get_latest_completed_snapshot_date(portfolio_id, security_id, 0)
    # Query for epoch 1, which has only one snapshot
    result_epoch_1 = await repo.get_latest_completed_snapshot_date(portfolio_id, security_id, 1)
    # Query for an epoch with no snapshots
    result_epoch_2 = await repo.get_latest_completed_snapshot_date(portfolio_id, security_id, 2)

    # ASSERT
    assert result_epoch_0 == date(2025, 8, 5)
    assert result_epoch_1 == date(2025, 8, 10)
    assert result_epoch_2 is None


async def test_get_latest_position_history_date(
    clean_db, setup_position_history_date_data, async_db_session: AsyncSession
):
    """
    GIVEN position history exists for a key in different epochs
    WHEN get_latest_position_history_date is called for a specific epoch
    THEN it should return the max date for only that epoch.
    """
    repo = PositionRepository(async_db_session)
    portfolio_id = "POS_HIST_DATE_TEST_01"
    security_id = "S1"

    result_epoch_0 = await repo.get_latest_position_history_date(portfolio_id, security_id, 0)
    result_epoch_1 = await repo.get_latest_position_history_date(portfolio_id, security_id, 1)
    result_epoch_2 = await repo.get_latest_position_history_date(portfolio_id, security_id, 2)

    assert result_epoch_0 == date(2025, 8, 6)
    assert result_epoch_1 == date(2025, 8, 9)
    assert result_epoch_2 is None
