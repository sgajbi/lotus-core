# tests/unit/services/timeseries-generator-service/core/test_position_timeseries_logic.py
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    DailyPositionSnapshot,
)

from src.services.timeseries_generator_service.app.core.position_timeseries_logic import (
    PositionTimeseriesLogic,
)


@pytest.fixture
def current_snapshot() -> DailyPositionSnapshot:
    """A fixture for the current day's position snapshot."""
    return DailyPositionSnapshot(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 29),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("10000"),
        market_value_local=Decimal("12000"),
    )


@pytest.fixture
def previous_day_snapshot() -> DailyPositionSnapshot:
    """
    A fixture for the previous day's snapshot record.
    """
    return DailyPositionSnapshot(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        quantity=Decimal("90"),
        cost_basis_local=Decimal("9000"),
        market_value_local=Decimal("11500"),
    )


def test_logic_sets_epoch_correctly(current_snapshot, previous_day_snapshot):
    """
    Tests that the epoch passed to the logic is set on the created record.
    """
    # ARRANGE
    cashflows = []

    # ACT
    new_record = PositionTimeseriesLogic.calculate_daily_record(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_day_snapshot,
        cashflows=cashflows,
        epoch=5,  # Test with a specific epoch
    )

    # ASSERT
    assert new_record.epoch == 5


def test_logic_with_portfolio_and_position_flows(current_snapshot, previous_day_snapshot):
    """
    Tests that logic correctly segregates cashflows based on their boolean flags.
    """
    # ARRANGE: A list of cashflows with mixed flags
    cashflows = [
        # A BUY: only a position flow
        Cashflow(
            amount=Decimal(1000), timing="BOD", is_position_flow=True, is_portfolio_flow=False
        ),
        # A FEE: both a position and portfolio flow
        Cashflow(amount=Decimal(-50), timing="EOD", is_position_flow=True, is_portfolio_flow=True),
    ]

    # ACT
    new_record = PositionTimeseriesLogic.calculate_daily_record(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_day_snapshot,
        cashflows=cashflows,
        epoch=0,
    )

    # ASSERT
    assert new_record.bod_market_value == Decimal("11500")
    assert new_record.eod_market_value == Decimal("12000")
    assert new_record.bod_cashflow_position == Decimal("1000")
    assert new_record.bod_cashflow_portfolio == Decimal("0")
    assert new_record.eod_cashflow_position == Decimal("-50")
    assert new_record.eod_cashflow_portfolio == Decimal("-50")
