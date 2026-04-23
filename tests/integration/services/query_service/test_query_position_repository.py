# tests/integration/services/query_service/test_query_position_repository.py
from datetime import date, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_test_data(db_engine):
    """Sets up a portfolio with a security having two position snapshots on different days."""
    with Session(db_engine) as session:
        # Create prerequisite data
        portfolio = Portfolio(
            portfolio_id="POS_REPO_TEST_01",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
        instrument = Instrument(
            security_id="SEC_POS_TEST_01",
            name="TestSec",
            isin="XS1234567890",
            currency="USD",
            product_type="Stock",
            asset_class="Equity",
            sector="Technology",
            country_of_risk="US",
        )
        session.add_all([portfolio, instrument])
        session.flush()

        # Create the corresponding PositionState record
        position_state = PositionState(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            epoch=0,
            watermark_date=date(2024, 1, 1),
            status="CURRENT",
        )
        session.add(position_state)

        # Create two snapshots for the same security on different days
        today = date.today()
        yesterday = today - timedelta(days=1)

        snapshot_yesterday = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            date=yesterday,
            quantity=Decimal("100"),
            cost_basis=Decimal("10000"),
            epoch=0,
        )
        snapshot_today = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            date=today,
            quantity=Decimal("110"),
            cost_basis=Decimal("11000"),
            epoch=0,
        )
        transaction = Transaction(
            transaction_id="POS-REPO-TXN-01",
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            instrument_id="SEC_POS_TEST_01",
            transaction_date=today,
            transaction_type="BUY",
            quantity=Decimal("110"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("11000"),
            trade_currency="USD",
            currency="USD",
        )
        history = PositionHistory(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            transaction_id="POS-REPO-TXN-01",
            position_date=today,
            quantity=Decimal("110"),
            cost_basis=Decimal("11000"),
            epoch=0,
        )
        session.add(transaction)
        session.flush()
        session.add_all([history, snapshot_yesterday, snapshot_today])
        session.commit()

    return {"today": today, "yesterday": yesterday}


@pytest.fixture(scope="function")
def setup_held_since_data(db_engine):
    """Sets up a broken holding period (BUY -> SELL -> BUY) for a security."""
    portfolio_id = "HELD_SINCE_P1"
    security_id = "HELD_SINCE_S1"
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
                security_id=security_id,
                instrument_id="I1",
                transaction_date=date(2025, 1, 1),
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
                transaction_id="T2",
                portfolio_id=portfolio_id,
                security_id=security_id,
                instrument_id="I1",
                transaction_date=date(2025, 1, 1),
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
                security_id=security_id,
                instrument_id="I1",
                transaction_date=date(2025, 1, 1),
                transaction_type="BUY",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.commit()

        # History: Buy on Mar 1, Sell on Mar 15 (quantity -> 0), Buy again on Apr 1
        history = [
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="T1",
                epoch=0,
                position_date=date(2025, 3, 1),
                quantity=Decimal("100"),
                cost_basis=Decimal("1000"),
            ),
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="T2",
                epoch=0,
                position_date=date(2025, 3, 15),
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
            ),
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="T3",
                epoch=0,
                position_date=date(2025, 4, 1),
                quantity=Decimal("50"),
                cost_basis=Decimal("550"),
            ),
        ]
        session.add_all(history)
        session.commit()


async def test_get_latest_positions_by_portfolio(
    clean_db, setup_test_data, async_db_session: AsyncSession
):
    """
    GIVEN a security with multiple historical daily snapshots in the database
    WHEN get_latest_positions_by_portfolio is called
    THEN it should return only the single, most recent snapshot for that
    security, including all instrument data.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "POS_REPO_TEST_01"

    # ACT
    latest_positions = await repo.get_latest_positions_by_portfolio(portfolio_id)

    # ASSERT
    assert len(latest_positions) == 1

    latest_snapshot, instrument, pos_state = latest_positions[0]

    assert latest_snapshot.portfolio_id == portfolio_id
    assert latest_snapshot.security_id == "SEC_POS_TEST_01"
    assert latest_snapshot.date == setup_test_data["today"]
    assert latest_snapshot.quantity == Decimal("110")
    assert instrument.name == "TestSec"
    assert pos_state.status == "CURRENT"
    assert instrument.asset_class == "Equity"
    assert instrument.isin == "XS1234567890"
    assert instrument.currency == "USD"
    assert instrument.sector == "Technology"
    assert instrument.country_of_risk == "US"
    assert latest_snapshot.epoch == 0


async def test_get_held_since_date(clean_db, setup_held_since_data, async_db_session: AsyncSession):
    """
    GIVEN a position history with a period of zero quantity
    WHEN get_held_since_date is called
    THEN it should return the date of the first transaction that re-opened the position.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "HELD_SINCE_P1"
    security_id = "HELD_SINCE_S1"

    # ACT
    held_since = await repo.get_held_since_date(portfolio_id, security_id, 0)

    # ASSERT
    # The last zero quantity was on Mar 15. The next transaction was on Apr 1.
    assert held_since == date(2025, 4, 1)


@pytest.fixture(scope="function")
def setup_snapshot_id_order_mismatch_data(db_engine):
    """
    Inserts an older business-date snapshot after a newer one to ensure latest selection
    is based on date, not surrogate id ordering.
    """
    portfolio_id = "POS_REPO_TEST_02"
    security_id = "SEC_POS_TEST_02"
    with Session(db_engine) as session:
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
            Instrument(
                security_id=security_id,
                name="TestSec2",
                isin="XS0000000002",
                currency="USD",
                product_type="Stock",
                asset_class="Equity",
                sector="Tech",
                country_of_risk="US",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=0,
                watermark_date=date(2024, 1, 1),
                status="CURRENT",
            )
        )
        session.flush()

        newer_date = date(2025, 1, 10)
        older_date = date(2025, 1, 9)
        session.add(
            Transaction(
                transaction_id="POS-REPO-TXN-02",
                portfolio_id=portfolio_id,
                security_id=security_id,
                instrument_id=security_id,
                transaction_date=newer_date,
                transaction_type="BUY",
                quantity=Decimal("200"),
                price=Decimal("100"),
                gross_transaction_amount=Decimal("20000"),
                trade_currency="USD",
                currency="USD",
            )
        )
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="POS-REPO-TXN-02",
                position_date=newer_date,
                quantity=Decimal("200"),
                cost_basis=Decimal("20000"),
                epoch=0,
            )
        )
        session.add(
            DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=newer_date,
                quantity=Decimal("200"),
                cost_basis=Decimal("20000"),
                epoch=0,
            )
        )
        session.flush()
        session.add(
            DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=older_date,
                quantity=Decimal("150"),
                cost_basis=Decimal("15000"),
                epoch=0,
            )
        )
        session.commit()
    return {"portfolio_id": portfolio_id, "newer_date": newer_date}


async def test_get_latest_positions_prefers_latest_business_date_over_latest_id(
    clean_db, setup_snapshot_id_order_mismatch_data, async_db_session: AsyncSession
):
    repo = PositionRepository(async_db_session)
    portfolio_id = setup_snapshot_id_order_mismatch_data["portfolio_id"]

    latest_positions = await repo.get_latest_positions_by_portfolio(portfolio_id)

    assert len(latest_positions) == 1
    latest_snapshot, _, _ = latest_positions[0]
    assert latest_snapshot.date == setup_snapshot_id_order_mismatch_data["newer_date"]
    assert latest_snapshot.quantity == Decimal("200")


@pytest.fixture(scope="function")
def setup_as_of_positive_filter_data(db_engine):
    portfolio_id = "POS_REPO_TEST_03"
    positive_security = "SEC_POS_POSITIVE"
    negative_security = "SEC_POS_NEGATIVE"
    as_of_date = date(2025, 1, 10)

    with Session(db_engine) as session:
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
        session.add_all(
            [
                Instrument(
                    security_id=positive_security,
                    name="Positive",
                    isin="XS0000000011",
                    currency="USD",
                    product_type="Stock",
                    asset_class="Equity",
                    sector="Tech",
                    country_of_risk="US",
                ),
                Instrument(
                    security_id=negative_security,
                    name="Negative",
                    isin="XS0000000012",
                    currency="USD",
                    product_type="Cash",
                    asset_class="Cash",
                    sector=None,
                    country_of_risk="US",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id=positive_security,
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id=negative_security,
                    epoch=1,
                    watermark_date=date(2024, 1, 1),
                    status="REPROCESSING",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Transaction(
                    transaction_id="POS-REPO-TXN-03-POS",
                    portfolio_id=portfolio_id,
                    security_id=positive_security,
                    instrument_id=positive_security,
                    transaction_date=as_of_date,
                    transaction_type="BUY",
                    quantity=Decimal("25"),
                    price=Decimal("100"),
                    gross_transaction_amount=Decimal("2500"),
                    trade_currency="USD",
                    currency="USD",
                ),
                Transaction(
                    transaction_id="POS-REPO-TXN-03-NEG",
                    portfolio_id=portfolio_id,
                    security_id=negative_security,
                    instrument_id=negative_security,
                    transaction_date=as_of_date,
                    transaction_type="BUY",
                    quantity=Decimal("-10"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("-10"),
                    trade_currency="USD",
                    currency="USD",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=positive_security,
                    transaction_id="POS-REPO-TXN-03-POS",
                    position_date=as_of_date,
                    quantity=Decimal("25"),
                    cost_basis=Decimal("2500"),
                    epoch=0,
                ),
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=negative_security,
                    transaction_id="POS-REPO-TXN-03-NEG",
                    position_date=as_of_date,
                    quantity=Decimal("-10"),
                    cost_basis=Decimal("-10"),
                    epoch=1,
                ),
                DailyPositionSnapshot(
                    portfolio_id=portfolio_id,
                    security_id=positive_security,
                    date=as_of_date,
                    quantity=Decimal("25"),
                    cost_basis=Decimal("2500"),
                    epoch=0,
                ),
                DailyPositionSnapshot(
                    portfolio_id=portfolio_id,
                    security_id=negative_security,
                    date=as_of_date,
                    quantity=Decimal("-10"),
                    cost_basis=Decimal("-10"),
                    epoch=1,
                ),
            ]
        )
        session.commit()

    return {"portfolio_id": portfolio_id, "as_of_date": as_of_date}


async def test_get_latest_positions_by_portfolio_as_of_date_keeps_negative_open_positions(
    clean_db, setup_as_of_positive_filter_data, async_db_session: AsyncSession
):
    repo = PositionRepository(async_db_session)

    latest_positions = await repo.get_latest_positions_by_portfolio_as_of_date(
        setup_as_of_positive_filter_data["portfolio_id"],
        setup_as_of_positive_filter_data["as_of_date"],
    )

    assert len(latest_positions) == 2
    by_security = {
        snapshot.security_id: (snapshot, instrument, pos_state)
        for snapshot, instrument, pos_state in latest_positions
    }

    positive_snapshot, positive_instrument, positive_state = by_security["SEC_POS_POSITIVE"]
    assert positive_snapshot.quantity == Decimal("25")
    assert positive_instrument.name == "Positive"
    assert positive_state.status == "CURRENT"

    negative_snapshot, negative_instrument, negative_state = by_security["SEC_POS_NEGATIVE"]
    assert negative_snapshot.quantity == Decimal("-10")
    assert negative_instrument.name == "Negative"
    assert negative_state.status == "REPROCESSING"


@pytest.fixture(scope="function")
def setup_stale_snapshot_reconciliation_data(db_engine):
    portfolio_id = "POS_REPO_STALE_RECON"
    security_id = "SEC_POS_STALE_RECON"
    as_of_date = date(2026, 4, 22)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="medium",
                portfolio_type="discretionary",
                booking_center_code="SGPB",
                client_id="C1",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="Reconciled Bond",
                isin="XS0000000099",
                currency="USD",
                product_type="Bond",
                asset_class="Fixed Income",
                sector="Government",
                country_of_risk="US",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id,
                epoch=2,
                watermark_date=as_of_date,
                status="CURRENT",
            )
        )
        session.add(
            Transaction(
                transaction_id="POS-RECON-TXN-01",
                portfolio_id=portfolio_id,
                security_id=security_id,
                instrument_id=security_id,
                transaction_date=date(2026, 3, 11),
                transaction_type="BUY",
                quantity=Decimal("180"),
                price=Decimal("992.8"),
                gross_transaction_amount=Decimal("178704"),
                trade_currency="USD",
                currency="USD",
            )
        )
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="POS-RECON-TXN-01",
                position_date=date(2026, 3, 11),
                quantity=Decimal("180"),
                cost_basis=Decimal("178704"),
                epoch=2,
            )
        )
        session.flush()
        session.add_all(
            [
                DailyPositionSnapshot(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    date=as_of_date,
                    quantity=Decimal("0"),
                    cost_basis=Decimal("0"),
                    market_price=Decimal("101.35"),
                    market_value=Decimal("0"),
                    epoch=2,
                ),
                DailyPositionSnapshot(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    date=date(2026, 4, 10),
                    quantity=Decimal("180"),
                    cost_basis=Decimal("178704"),
                    market_price=Decimal("101.35"),
                    market_value=Decimal("182430"),
                    epoch=2,
                ),
            ]
        )
        session.commit()

    return {"portfolio_id": portfolio_id, "security_id": security_id, "as_of_date": as_of_date}


async def test_get_latest_positions_ignores_stale_snapshot_quantity_after_replay(
    clean_db,
    setup_stale_snapshot_reconciliation_data,
    async_db_session: AsyncSession,
):
    repo = PositionRepository(async_db_session)

    latest_positions = await repo.get_latest_positions_by_portfolio_as_of_date(
        setup_stale_snapshot_reconciliation_data["portfolio_id"],
        setup_stale_snapshot_reconciliation_data["as_of_date"],
    )

    assert len(latest_positions) == 1
    snapshot, instrument, position_state = latest_positions[0]
    assert snapshot.security_id == setup_stale_snapshot_reconciliation_data["security_id"]
    assert snapshot.date == date(2026, 4, 10)
    assert snapshot.quantity == Decimal("180")
    assert snapshot.market_value == Decimal("182430")
    assert instrument.name == "Reconciled Bond"
    assert position_state.status == "CURRENT"
