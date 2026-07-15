"""Domain tests for deterministic position-timeseries calculation."""

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from src.services.portfolio_derived_state_service.app.domain.position_timeseries.calculator import (
    calculate_position_timeseries,
)
from src.services.portfolio_derived_state_service.app.domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
)

BUSINESS_DATE = date(2025, 7, 29)


@pytest.fixture
def current_snapshot() -> PositionSnapshotRecord:
    """Return a valued end-of-day position state."""

    return PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=BUSINESS_DATE,
        epoch=5,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("10000"),
        market_value_local=Decimal("12000"),
    )


@pytest.fixture
def previous_snapshot() -> PositionSnapshotRecord:
    """Return the immediately preceding valued position state."""

    return PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        epoch=5,
        quantity=Decimal("90"),
        cost_basis_local=Decimal("9000"),
        market_value_local=Decimal("11500"),
    )


def _cashflow(
    *,
    amount: Decimal,
    classification: str,
    timing: str,
    is_position_flow: bool,
    is_portfolio_flow: bool,
    transaction_id: str = "T1",
) -> PositionCashflowRecord:
    return PositionCashflowRecord(
        transaction_id=transaction_id,
        cashflow_date=BUSINESS_DATE,
        epoch=5,
        amount=amount,
        classification=classification,
        timing=timing,
        is_position_flow=is_position_flow,
        is_portfolio_flow=is_portfolio_flow,
    )


def test_calculation_uses_requested_epoch(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=8,
    )

    assert record.epoch == 8


def test_first_position_day_has_zero_beginning_market_value(
    current_snapshot: PositionSnapshotRecord,
) -> None:
    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=None,
        cashflows=[],
        epoch=5,
    )

    assert record.bod_market_value == Decimal("0")


def test_calculation_separates_position_and_portfolio_cashflows(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("1000"),
            timing="BOD",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=Decimal("-50"),
            timing="EOD",
            classification=" expense ",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=5,
    )

    assert record.bod_market_value == Decimal("11500")
    assert record.eod_market_value == Decimal("12000")
    assert record.bod_cashflow_position == Decimal("1000")
    assert record.bod_cashflow_portfolio == Decimal("0")
    assert record.eod_cashflow_position == Decimal("-50")
    assert record.eod_cashflow_portfolio == Decimal("-50")
    assert record.fees == Decimal("50")


def test_calculation_defensively_normalizes_numeric_text_and_blank_amounts() -> None:
    current_snapshot = PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=BUSINESS_DATE,
        epoch=6,
        quantity=cast(Decimal, "100"),
        cost_basis_local=cast(Decimal, "10000"),
        market_value_local=cast(Decimal, "12000"),
    )
    previous_snapshot = PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        epoch=6,
        quantity=Decimal("90"),
        cost_basis_local=Decimal("9000"),
        market_value_local=cast(Decimal, "11500"),
    )
    cashflows = [
        _cashflow(
            amount=cast(Decimal, "1000"),
            timing="BOD",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=cast(Decimal, " "),
            timing="EOD",
            classification="EXPENSE",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=6,
    )

    assert record.bod_market_value == Decimal("11500")
    assert record.eod_market_value == Decimal("12000")
    assert record.cost == Decimal("100")
    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_portfolio == Decimal("0")
    assert record.fees == Decimal("0")


def test_zero_quantity_produces_zero_average_cost(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    zero_quantity_snapshot = PositionSnapshotRecord(
        portfolio_id=current_snapshot.portfolio_id,
        security_id=current_snapshot.security_id,
        date=current_snapshot.date,
        epoch=current_snapshot.epoch,
        quantity=Decimal("0"),
        cost_basis_local=Decimal("10000"),
        market_value_local=Decimal("0"),
    )

    record = calculate_position_timeseries(
        current_snapshot=zero_quantity_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=8,
    )

    assert record.quantity == Decimal("0")
    assert record.cost == Decimal("0")


def test_cashflow_timing_is_canonicalized_before_bucketing(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("1000"),
            timing=" bod ",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=True,
        )
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=7,
    )

    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_position == Decimal("0")
    assert record.bod_cashflow_portfolio == Decimal("1000")
    assert record.eod_cashflow_portfolio == Decimal("0")


def test_product_leg_signs_are_normalized_for_attribution(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("-1000"),
            classification=" investment_outflow ",
            timing="BOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=Decimal("250"),
            classification="INCOME",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
            transaction_id="T2",
        ),
        _cashflow(
            amount=Decimal("-1000"),
            classification="TRANSFER",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
            transaction_id="T3",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=5,
    )

    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_position == Decimal("-1250")


def test_expense_fees_do_not_reclassify_external_withdrawals(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("-25000"),
            classification="CASHFLOW_OUT",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=True,
        ),
        _cashflow(
            amount=Decimal("-275"),
            classification="EXPENSE",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=14,
    )

    assert record.eod_cashflow_portfolio == Decimal("-25275")
    assert record.fees == Decimal("275")
