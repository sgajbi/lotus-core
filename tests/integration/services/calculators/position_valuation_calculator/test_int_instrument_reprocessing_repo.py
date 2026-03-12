# tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py  # noqa: E501
from datetime import date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    InstrumentReprocessingState,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_reprocessing_trigger_data(db_engine, clean_db):
    """
    Seeds the database with instrument triggers and related portfolio positions.
    """
    with Session(db_engine) as session:
        # Prerequisites
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
        session.flush()

        # Position States: P1 holds S1, P2 holds S1 and S2
        session.add_all(
            [
                PositionState(
                    portfolio_id="P1", security_id="S1", epoch=0, watermark_date=date(2025, 1, 1)
                ),
                PositionState(
                    portfolio_id="P2", security_id="S1", epoch=0, watermark_date=date(2025, 1, 1)
                ),
                PositionState(
                    portfolio_id="P2", security_id="S2", epoch=0, watermark_date=date(2025, 1, 1)
                ),
            ]
        )

        # Reprocessing Triggers
        session.add_all(
            [
                InstrumentReprocessingState(
                    security_id="S1", earliest_impacted_date=date(2025, 8, 10)
                ),
                InstrumentReprocessingState(
                    security_id="S2", earliest_impacted_date=date(2025, 8, 11)
                ),
            ]
        )
        session.commit()


async def test_get_instrument_reprocessing_triggers(
    setup_reprocessing_trigger_data, async_db_session: AsyncSession
):
    """
    GIVEN pending instrument reprocessing triggers in the database
    WHEN get_instrument_reprocessing_triggers is called
    THEN it should fetch the triggers ordered by earliest impacted date first.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)

    # ACT
    triggers = await repo.get_instrument_reprocessing_triggers(batch_size=5)

    # ASSERT
    assert len(triggers) == 2
    security_ids = {t.security_id for t in triggers}
    assert "S1" in security_ids
    assert "S2" in security_ids
    assert [t.security_id for t in triggers] == ["S1", "S2"]


async def test_get_instrument_reprocessing_triggers_prioritizes_oldest_impacted_date(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN multiple pending instrument reprocessing triggers
    WHEN get_instrument_reprocessing_triggers is called
    THEN the scheduler-facing order should prioritize the oldest impacted date,
    with updated_at and security_id only acting as tie-breakers.
    """
    with Session(db_engine) as session:
        session.add_all(
            [
                InstrumentReprocessingState(
                    security_id="S_LATE",
                    earliest_impacted_date=date(2025, 8, 11),
                ),
                InstrumentReprocessingState(
                    security_id="S_EARLY",
                    earliest_impacted_date=date(2025, 8, 9),
                ),
                InstrumentReprocessingState(
                    security_id="S_MID",
                    earliest_impacted_date=date(2025, 8, 10),
                ),
            ]
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    triggers = await repo.get_instrument_reprocessing_triggers(batch_size=10)

    assert [t.security_id for t in triggers] == ["S_EARLY", "S_MID", "S_LATE"]


async def test_find_portfolios_for_security(
    setup_reprocessing_trigger_data, async_db_session: AsyncSession
):
    """
    GIVEN position state records linking portfolios to securities
    WHEN find_portfolios_for_security is called
    THEN it should return all unique portfolio IDs associated with that security.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)

    # ACT
    portfolios_for_s1 = await repo.find_portfolios_for_security("S1")
    portfolios_for_s2 = await repo.find_portfolios_for_security("S2")

    # ASSERT
    assert len(portfolios_for_s1) == 2
    assert set(portfolios_for_s1) == {"P1", "P2"}

    assert len(portfolios_for_s2) == 1
    assert portfolios_for_s2[0] == "P2"


async def test_find_portfolios_holding_security_on_date_excludes_pre_impact_closed_positions(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN portfolios that held a security at different times
    WHEN find_portfolios_holding_security_on_date is called for an impacted date
    THEN only portfolios holding the security on or before that date should be returned.
    """
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    portfolio_id="P_HELD",
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
                    portfolio_id="P_CLOSED_BEFORE",
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
                    portfolio_id="P_NOT_YET_OPEN",
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
        session.flush()
        session.add_all(
            [
                Transaction(
                    transaction_id="TX-P-HELD-1",
                    portfolio_id="P_HELD",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 9, 9, 0, 0),
                ),
                Transaction(
                    transaction_id="TX-P-CLOSED-1",
                    portfolio_id="P_CLOSED_BEFORE",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 1, 9, 0, 0),
                ),
                Transaction(
                    transaction_id="TX-P-CLOSED-2",
                    portfolio_id="P_CLOSED_BEFORE",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="SELL",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 8, 9, 0, 0),
                ),
                Transaction(
                    transaction_id="TX-P-NOTYET-1",
                    portfolio_id="P_NOT_YET_OPEN",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 11, 9, 0, 0),
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id="P_HELD",
                    security_id="S1",
                    transaction_id="TX-P-HELD-1",
                    epoch=0,
                    position_date=date(2025, 8, 9),
                    quantity=100,
                    cost_basis=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id="P_CLOSED_BEFORE",
                    security_id="S1",
                    transaction_id="TX-P-CLOSED-1",
                    epoch=0,
                    position_date=date(2025, 8, 1),
                    quantity=100,
                    cost_basis=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id="P_CLOSED_BEFORE",
                    security_id="S1",
                    transaction_id="TX-P-CLOSED-2",
                    epoch=0,
                    position_date=date(2025, 8, 8),
                    quantity=0,
                    cost_basis=Decimal("0"),
                ),
                PositionHistory(
                    portfolio_id="P_NOT_YET_OPEN",
                    security_id="S1",
                    transaction_id="TX-P-NOTYET-1",
                    epoch=0,
                    position_date=date(2025, 8, 11),
                    quantity=100,
                    cost_basis=Decimal("100"),
                ),
            ]
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    portfolios = await repo.find_portfolios_holding_security_on_date("S1", date(2025, 8, 10))

    assert portfolios == ["P_HELD"]


async def test_delete_instrument_reprocessing_triggers(
    setup_reprocessing_trigger_data, async_db_session: AsyncSession
):
    """
    GIVEN existing instrument reprocessing triggers
    WHEN delete_instrument_reprocessing_triggers is called
    THEN the specified records should be removed from the database.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)
    security_id_to_delete = "S1"

    # ACT
    await repo.delete_instrument_reprocessing_triggers([(security_id_to_delete, date(2025, 8, 10))])
    await async_db_session.commit()

    # ASSERT
    remaining_triggers = await repo.get_instrument_reprocessing_triggers(batch_size=5)

    assert len(remaining_triggers) == 1
    assert remaining_triggers[0].security_id == "S2"


async def test_delete_instrument_reprocessing_triggers_is_fenced_by_impacted_date(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN a scheduler fetched a trigger for a security at one impacted date
    AND a newer back-dated event lowered the impacted date before delete
    WHEN delete_instrument_reprocessing_triggers is called with the stale fence
    THEN the newer trigger row must survive the delete.
    """
    with Session(db_engine) as session:
        session.add(
            InstrumentReprocessingState(
                security_id="S1",
                earliest_impacted_date=date(2025, 8, 10),
            )
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    # Simulate a newer trigger arriving between scheduler fetch and delete.
    with Session(db_engine) as session:
        trigger = session.get(InstrumentReprocessingState, "S1")
        trigger.earliest_impacted_date = date(2025, 8, 8)
        session.commit()

    await repo.delete_instrument_reprocessing_triggers([("S1", date(2025, 8, 10))])
    await async_db_session.commit()

    remaining_triggers = await repo.get_instrument_reprocessing_triggers(batch_size=5)

    assert len(remaining_triggers) == 1
    assert remaining_triggers[0].security_id == "S1"
    assert remaining_triggers[0].earliest_impacted_date == date(2025, 8, 8)
