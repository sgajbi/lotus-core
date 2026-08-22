"""Tests for durable cost-basis open-lot state."""

from datetime import date
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AmortizedCostCarryState,
    OpenLotState,
)


def _carry_state() -> AmortizedCostCarryState:
    return AmortizedCostCarryState(
        profile_id="PROFILE-1",
        profile_version=2,
        profile_content_hash="a" * 64,
        recognized_through_date=date(2026, 6, 30),
        scheduled_cost_local=Decimal("97.0000000000"),
        carrying_amount_local=Decimal("64.6666666667"),
        carrying_amount_base=Decimal("79.8353902264"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )


def test_open_lot_preserves_amortized_recognition_baseline() -> None:
    state = OpenLotState(
        original_quantity=Decimal("3"),
        quantity=Decimal("2"),
        cost_local=Decimal("64.6666666667"),
        cost_base=Decimal("79.8353902264"),
        amortized_cost=_carry_state(),
    )

    assert state.amortized_cost == _carry_state()


def test_closed_lot_rejects_stale_amortized_carry_state() -> None:
    with pytest.raises(ValueError, match="closed lot state"):
        OpenLotState(
            original_quantity=Decimal("2"),
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
            amortized_cost=_carry_state(),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("quantity", Decimal("-1"), ValueError),
        ("cost_local", Decimal("NaN"), ValueError),
        ("cost_base", "1", TypeError),
    ],
)
def test_open_lot_rejects_invalid_numeric_state(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    inputs: dict[str, object] = {
        "original_quantity": Decimal("1"),
        "quantity": Decimal("1"),
        "cost_local": Decimal("1"),
        "cost_base": Decimal("1"),
    }
    inputs[field_name] = value

    with pytest.raises(error_type):
        OpenLotState(**inputs)  # type: ignore[arg-type]


def test_open_lot_rejects_open_quantity_above_original_authority() -> None:
    with pytest.raises(ValueError, match="must not exceed original_quantity"):
        OpenLotState(
            original_quantity=Decimal("1"),
            quantity=Decimal("2"),
            cost_local=Decimal("1"),
            cost_base=Decimal("1"),
        )


def test_carry_state_rejects_incomplete_identity_and_invalid_amount() -> None:
    with pytest.raises(ValueError, match="profile_id"):
        AmortizedCostCarryState(
            profile_id=" ",
            profile_version=1,
            profile_content_hash="a" * 64,
            recognized_through_date=date(2026, 6, 30),
            scheduled_cost_local=Decimal("97"),
            carrying_amount_local=Decimal("64"),
            carrying_amount_base=Decimal("64"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )
    with pytest.raises(ValueError, match="scheduled_cost_local"):
        AmortizedCostCarryState(
            profile_id="PROFILE-1",
            profile_version=1,
            profile_content_hash="a" * 64,
            recognized_through_date=date(2026, 6, 30),
            scheduled_cost_local=Decimal("-0.01"),
            carrying_amount_local=Decimal("64"),
            carrying_amount_base=Decimal("64"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )

    with pytest.raises(ValueError, match="carrying_amount_local"):
        AmortizedCostCarryState(
            profile_id="PROFILE-1",
            profile_version=1,
            profile_content_hash="a" * 64,
            recognized_through_date=date(2026, 6, 30),
            scheduled_cost_local=Decimal("97"),
            carrying_amount_local=Decimal("-0.01"),
            carrying_amount_base=Decimal("64"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )
