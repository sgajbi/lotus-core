# tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py  # noqa: E501
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    InstrumentReprocessingState,
    Portfolio,
    PositionHistory,
    PositionState,
    Transaction,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def setup_reprocessing_trigger_data(async_db_session: AsyncSession, clean_db):
    """
    Seeds the database with instrument triggers and related portfolio positions.
    """
    async_db_session.add_all(
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
            PositionState(
                portfolio_id="P1", security_id="S1", epoch=0, watermark_date=date(2025, 1, 1)
            ),
            PositionState(
                portfolio_id="P2", security_id="S1", epoch=0, watermark_date=date(2025, 1, 1)
            ),
            PositionState(
                portfolio_id="P2", security_id="S2", epoch=0, watermark_date=date(2025, 1, 1)
            ),
            InstrumentReprocessingState(
                security_id="S1", earliest_impacted_date=date(2025, 8, 10)
            ),
            InstrumentReprocessingState(
                security_id="S2", earliest_impacted_date=date(2025, 8, 11)
            ),
        ]
    )
    await async_db_session.commit()


async def test_claim_instrument_reprocessing_triggers(
    setup_reprocessing_trigger_data, async_db_session: AsyncSession
):
    """
    GIVEN pending instrument reprocessing triggers in the database
    WHEN claim_instrument_reprocessing_triggers is called
    THEN it should atomically consume the triggers ordered by earliest impacted date first.
    """
    repo = ValuationRepository(async_db_session)

    triggers = await repo.claim_instrument_reprocessing_triggers(batch_size=5)
    await async_db_session.commit()

    assert len(triggers) == 2
    assert [t.security_id for t in triggers] == ["S1", "S2"]

    remaining_triggers = (
        (
            await async_db_session.execute(
                select(InstrumentReprocessingState).order_by(
                    InstrumentReprocessingState.security_id.asc()
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_triggers == []


async def test_claim_instrument_reprocessing_triggers_prioritizes_oldest_impacted_date(
    async_db_session: AsyncSession, clean_db
):
    """
    GIVEN multiple pending instrument reprocessing triggers
    WHEN claim_instrument_reprocessing_triggers is called
    THEN the scheduler-facing order should prioritize the oldest impacted date,
    with updated_at and security_id only acting as tie-breakers.
    """
    async_db_session.add_all(
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
    await async_db_session.commit()

    repo = ValuationRepository(async_db_session)

    triggers = await repo.claim_instrument_reprocessing_triggers(batch_size=10)
    await async_db_session.commit()

    assert [t.security_id for t in triggers] == ["S_EARLY", "S_MID", "S_LATE"]


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
                PositionState(
                    portfolio_id="P_HELD",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P_CLOSED_BEFORE",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
                PositionState(
                    portfolio_id="P_NOT_YET_OPEN",
                    security_id="S1",
                    epoch=0,
                    watermark_date=date(2025, 8, 10),
                    status="CURRENT",
                ),
            ]
        )
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


async def test_find_portfolios_holding_security_on_date_uses_latest_history_on_or_before_date(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN a portfolio with multiple history rows before the impacted date
    WHEN the worker-facing lookup runs
    THEN the decision should be based on the latest history row on or before the date,
    not an older positive row.
    """
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id="P_MIXED",
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
        session.flush()
        session.add(
            PositionState(
                portfolio_id="P_MIXED",
                security_id="S1",
                epoch=0,
                watermark_date=date(2025, 8, 11),
                status="CURRENT",
            )
        )
        session.add_all(
            [
                Transaction(
                    transaction_id="TX-OPEN",
                    portfolio_id="P_MIXED",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 5, 9, 0, 0),
                ),
                Transaction(
                    transaction_id="TX-CLOSE",
                    portfolio_id="P_MIXED",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="SELL",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("100"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 9, 9, 0, 0),
                ),
                Transaction(
                    transaction_id="TX-REOPEN",
                    portfolio_id="P_MIXED",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="BUY",
                    quantity=Decimal("50"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("50"),
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
                    portfolio_id="P_MIXED",
                    security_id="S1",
                    transaction_id="TX-OPEN",
                    epoch=0,
                    position_date=date(2025, 8, 5),
                    quantity=100,
                    cost_basis=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id="P_MIXED",
                    security_id="S1",
                    transaction_id="TX-CLOSE",
                    epoch=0,
                    position_date=date(2025, 8, 9),
                    quantity=0,
                    cost_basis=Decimal("0"),
                ),
                PositionHistory(
                    portfolio_id="P_MIXED",
                    security_id="S1",
                    transaction_id="TX-REOPEN",
                    epoch=0,
                    position_date=date(2025, 8, 11),
                    quantity=50,
                    cost_basis=Decimal("50"),
                ),
            ]
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    portfolios_on_impact = await repo.find_portfolios_holding_security_on_date(
        "S1", date(2025, 8, 10)
    )
    portfolios_after_reopen = await repo.find_portfolios_holding_security_on_date(
        "S1", date(2025, 8, 11)
    )

    assert portfolios_on_impact == []
    assert portfolios_after_reopen == ["P_MIXED"]


async def test_find_portfolios_first_holding_security_after_date_returns_later_open_positions(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN a portfolio that first opens a security after the replay impacted date
    WHEN the worker fallback lookup runs
    THEN the portfolio should still be targeted for watermark reset because the
    earlier market data affects the first future-valued holding.
    """
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id="P_LATE_OPEN",
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
        session.flush()
        session.add(
            PositionState(
                portfolio_id="P_LATE_OPEN",
                security_id="S1",
                epoch=0,
                watermark_date=date(2025, 8, 12),
                status="CURRENT",
            )
        )
        session.add(
            Transaction(
                transaction_id="TX-LATE-OPEN",
                portfolio_id="P_LATE_OPEN",
                instrument_id="I-S1",
                security_id="S1",
                transaction_type="BUY",
                quantity=Decimal("100"),
                price=Decimal("1"),
                gross_transaction_amount=Decimal("100"),
                trade_currency="USD",
                currency="USD",
                transaction_date=datetime(2025, 8, 11, 9, 0, 0),
            )
        )
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id="P_LATE_OPEN",
                security_id="S1",
                transaction_id="TX-LATE-OPEN",
                epoch=0,
                position_date=date(2025, 8, 11),
                quantity=100,
                cost_basis=Decimal("100"),
            )
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    portfolios = await repo.find_portfolios_first_holding_security_after_date(
        "S1", date(2025, 8, 10)
    )

    assert portfolios == ["P_LATE_OPEN"]


async def test_find_portfolios_holding_security_on_date_ignores_stale_epochs(
    async_db_session: AsyncSession, db_engine, clean_db
):
    """
    GIVEN a portfolio with stale historical rows from an older epoch
    WHEN the worker-facing lookup runs
    THEN it must evaluate only the history attached to the current PositionState epoch.
    """
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id="P_EPOCH",
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
        session.flush()
        session.add(
            PositionState(
                portfolio_id="P_EPOCH",
                security_id="S1",
                epoch=1,
                watermark_date=date(2025, 8, 10),
                status="CURRENT",
            )
        )
        session.add_all(
            [
                Transaction(
                    transaction_id="TX-EPOCH-OLD",
                    portfolio_id="P_EPOCH",
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
                    transaction_id="TX-EPOCH-CURRENT",
                    portfolio_id="P_EPOCH",
                    instrument_id="I-S1",
                    security_id="S1",
                    transaction_type="SELL",
                    quantity=Decimal("0"),
                    price=Decimal("1"),
                    gross_transaction_amount=Decimal("0"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2025, 8, 8, 9, 0, 0),
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id="P_EPOCH",
                    security_id="S1",
                    transaction_id="TX-EPOCH-OLD",
                    epoch=0,
                    position_date=date(2025, 8, 9),
                    quantity=100,
                    cost_basis=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id="P_EPOCH",
                    security_id="S1",
                    transaction_id="TX-EPOCH-CURRENT",
                    epoch=1,
                    position_date=date(2025, 8, 8),
                    quantity=0,
                    cost_basis=Decimal("0"),
                ),
            ]
        )
        session.commit()

    repo = ValuationRepository(async_db_session)

    portfolios = await repo.find_portfolios_holding_security_on_date("S1", date(2025, 8, 10))

    assert portfolios == []
