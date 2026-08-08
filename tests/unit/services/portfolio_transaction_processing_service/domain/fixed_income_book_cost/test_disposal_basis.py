"""Tests for effective-dated amortized book-cost disposal allocation."""

from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output

from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AMORTIZED_COST_DISPOSAL_ALGORITHM_ID,
    AmortizedCostDisposalError,
    AmortizedCostEligibilityReason,
    CarriedLotBookCost,
    allocate_recognized_lot_book_cost,
    materialize_active_lot_amortized_cost_profile,
    materialize_parked_lot_amortized_cost_profile,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


def _active_profile():
    return materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )


@pytest.mark.parametrize(
    ("disposal_date", "expected_current", "expected_boundary"),
    [
        (date(2026, 1, 1), Decimal("97.0000000000"), date(2026, 1, 1)),
        (date(2026, 8, 1), Decimal("97.0000000000"), date(2026, 1, 1)),
        (date(2027, 1, 1), Decimal("100.0000000000"), date(2027, 1, 1)),
        (date(2028, 1, 1), Decimal("100.0000000000"), date(2027, 1, 1)),
    ],
)
def test_allocates_last_recognized_periodic_carrying_amount(
    disposal_date: date,
    expected_current: Decimal,
    expected_boundary: date,
) -> None:
    result = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=disposal_date,
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("100"),
        consumed_quantity=Decimal("40"),
        book_cost_fx_rate_to_base=Decimal("1.5"),
    )

    assert result.current_cost_local == expected_current
    assert result.recognized_through_date == expected_boundary
    assert result.consumed_cost_local == expected_current * Decimal("0.4")
    assert result.residual_cost_local == expected_current * Decimal("0.6")
    assert result.consumed_cost_local + result.residual_cost_local == expected_current
    assert result.consumed_quantity + result.residual_quantity == Decimal("100.0000000000")
    assert result.consumed_cost_base == result.consumed_cost_local * Decimal("1.5")
    assert result.consumed_cost_base + result.residual_cost_base == result.current_cost_base


def test_absorbs_all_rounding_residual_into_the_retained_lot() -> None:
    result = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 6, 30),
        original_quantity=Decimal("3"),
        open_quantity_before=Decimal("3"),
        consumed_quantity=Decimal("1"),
        book_cost_fx_rate_to_base=Decimal("1"),
    )

    assert result.consumed_cost_local == Decimal("32.3333333333")
    assert result.residual_cost_local == Decimal("64.6666666667")
    assert result.consumed_cost_local + result.residual_cost_local == Decimal("97.0000000000")
    assert result.retained_rounding_residual_local == Decimal("0.0000000000")


def test_carries_rounding_residual_into_terminal_disposal() -> None:
    first = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 6, 30),
        original_quantity=Decimal("3"),
        open_quantity_before=Decimal("3"),
        consumed_quantity=Decimal("1"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
    )
    second = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 7, 1),
        original_quantity=Decimal("3"),
        open_quantity_before=first.residual_quantity,
        consumed_quantity=Decimal("1"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
        carried_book_cost=first.carry_forward(),
    )
    terminal = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 7, 2),
        original_quantity=Decimal("3"),
        open_quantity_before=second.residual_quantity,
        consumed_quantity=Decimal("1"),
        book_cost_fx_rate_to_base=Decimal("1.2345678912"),
        carried_book_cost=second.carry_forward(),
    )

    assert [
        first.consumed_cost_local,
        second.consumed_cost_local,
        terminal.consumed_cost_local,
    ] == [
        Decimal("32.3333333333"),
        Decimal("32.3333333333"),
        Decimal("32.3333333334"),
    ]
    assert sum(
        (item.consumed_cost_local for item in (first, second, terminal)),
        Decimal(0),
    ) == Decimal("97.0000000000")
    assert (
        sum(
            (item.consumed_cost_base for item in (first, second, terminal)),
            Decimal(0),
        )
        == first.current_cost_base
    )
    assert terminal.residual_quantity == Decimal("0E-10")
    assert terminal.residual_cost_local == Decimal("0E-10")
    assert terminal.residual_cost_base == Decimal("0E-10")
    assert terminal.carry_forward() is None


def test_carried_basis_applies_only_newly_recognized_schedule_movement() -> None:
    first = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 6, 30),
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("100"),
        consumed_quantity=Decimal("40"),
        book_cost_fx_rate_to_base=Decimal("1"),
    )
    second = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2027, 1, 1),
        original_quantity=Decimal("100"),
        open_quantity_before=first.residual_quantity,
        consumed_quantity=Decimal("20"),
        book_cost_fx_rate_to_base=Decimal("1"),
        carried_book_cost=first.carry_forward(),
    )

    assert first.residual_cost_local == Decimal("58.2000000000")
    assert second.current_cost_local == Decimal("60.0000000000")
    assert second.consumed_cost_local == Decimal("20.0000000000")
    assert second.residual_cost_local == Decimal("40.0000000000")


def test_repeated_partial_disposal_is_deterministic_from_carried_state() -> None:
    first = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2026, 6, 30),
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("100"),
        consumed_quantity=Decimal("40"),
        book_cost_fx_rate_to_base=Decimal("1"),
    )
    second = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2027, 1, 1),
        original_quantity=Decimal("100"),
        open_quantity_before=first.residual_quantity,
        consumed_quantity=Decimal("20"),
        book_cost_fx_rate_to_base=Decimal("1"),
        carried_book_cost=first.carry_forward(),
    )
    restarted = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2027, 1, 1),
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("60"),
        consumed_quantity=Decimal("20"),
        book_cost_fx_rate_to_base=Decimal("1"),
        carried_book_cost=first.carry_forward(),
    )

    assert second == restarted
    assert second.current_cost_local == Decimal("60.0000000000")
    assert second.consumed_cost_local == Decimal("20.0000000000")
    assert second.residual_cost_local == Decimal("40.0000000000")
    assert second.residual_quantity == Decimal("40.0000000000")
    assert second.consumed_quantity + second.residual_quantity == second.open_quantity_before


def test_lineage_binds_profile_identity_inputs_and_outputs() -> None:
    result = allocate_recognized_lot_book_cost(
        _active_profile(),
        disposal_date=date(2027, 1, 1),
        original_quantity=Decimal("100"),
        open_quantity_before=Decimal("100"),
        consumed_quantity=Decimal("25"),
        book_cost_fx_rate_to_base=Decimal("1.25"),
    )

    assert result.calculation_lineage.algorithm_id == AMORTIZED_COST_DISPOSAL_ALGORITHM_ID
    assert calculation_lineage_binds_output(
        result.calculation_lineage,
        output_payload={
            "consumed_cost_base": result.consumed_cost_base,
            "consumed_cost_local": result.consumed_cost_local,
            "consumed_quantity": result.consumed_quantity,
            "current_cost_base": result.current_cost_base,
            "current_cost_local": result.current_cost_local,
            "open_quantity_before": result.open_quantity_before,
            "recognized_through_date": result.recognized_through_date,
            "residual_cost_base": result.residual_cost_base,
            "residual_cost_local": result.residual_cost_local,
            "residual_quantity": result.residual_quantity,
            "retained_rounding_residual_base": result.retained_rounding_residual_base,
            "retained_rounding_residual_local": result.retained_rounding_residual_local,
            "scheduled_cost_local": result.scheduled_cost_local,
        },
    )


def test_rejects_invalid_carried_basis() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        CarriedLotBookCost(
            scheduled_cost_local=Decimal("97"),
            residual_cost_local=Decimal("-0.01"),
            residual_cost_base=Decimal("1"),
        )
    with pytest.raises(TypeError, match="CarriedLotBookCost"):
        allocate_recognized_lot_book_cost(
            _active_profile(),
            disposal_date=date(2026, 6, 30),
            original_quantity=Decimal("100"),
            open_quantity_before=Decimal("100"),
            consumed_quantity=Decimal("10"),
            book_cost_fx_rate_to_base=Decimal("1"),
            carried_book_cost=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("original_quantity", Decimal("0"), ValueError),
        ("original_quantity", Decimal("NaN"), ValueError),
        ("original_quantity", 100, TypeError),
        ("open_quantity_before", Decimal("0"), ValueError),
        ("open_quantity_before", Decimal("NaN"), ValueError),
        ("open_quantity_before", 100, TypeError),
        ("consumed_quantity", Decimal("0"), ValueError),
        ("consumed_quantity", Decimal("Infinity"), ValueError),
        ("consumed_quantity", 10, TypeError),
        ("book_cost_fx_rate_to_base", Decimal("0"), ValueError),
        ("book_cost_fx_rate_to_base", Decimal("-1"), ValueError),
        ("book_cost_fx_rate_to_base", "1", TypeError),
    ],
)
def test_rejects_invalid_financial_inputs(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    inputs = {
        "original_quantity": Decimal("100"),
        "open_quantity_before": Decimal("100"),
        "consumed_quantity": Decimal("10"),
        "book_cost_fx_rate_to_base": Decimal("1"),
    }
    inputs[field_name] = value

    with pytest.raises(error_type):
        allocate_recognized_lot_book_cost(
            _active_profile(),
            disposal_date=date(2026, 6, 30),
            **inputs,  # type: ignore[arg-type]
        )


def test_rejects_overdisposal_and_preprofile_date() -> None:
    with pytest.raises(AmortizedCostDisposalError, match="must not exceed"):
        allocate_recognized_lot_book_cost(
            _active_profile(),
            disposal_date=date(2026, 6, 30),
            original_quantity=Decimal("10"),
            open_quantity_before=Decimal("10"),
            consumed_quantity=Decimal("11"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )
    with pytest.raises(AmortizedCostDisposalError, match="open_quantity_before"):
        allocate_recognized_lot_book_cost(
            _active_profile(),
            disposal_date=date(2026, 6, 30),
            original_quantity=Decimal("10"),
            open_quantity_before=Decimal("11"),
            consumed_quantity=Decimal("1"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )
    with pytest.raises(AmortizedCostDisposalError, match="must not precede"):
        allocate_recognized_lot_book_cost(
            _active_profile(),
            disposal_date=date(2025, 12, 31),
            original_quantity=Decimal("10"),
            open_quantity_before=Decimal("10"),
            consumed_quantity=Decimal("1"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )


def test_rejects_non_active_profile_instead_of_falling_back_to_original_cost() -> None:
    resolved = resolved_fixed_income_book_cost_inputs()
    parked = materialize_parked_lot_amortized_cost_profile(
        scope=resolved.assignment.scope,
        effective_date=resolved.assignment.valid_from,
        profile_version=1,
        reason=AmortizedCostEligibilityReason.CASHFLOW_SCHEDULE_MISSING,
    )

    with pytest.raises(AmortizedCostDisposalError, match="ACTIVE profile"):
        allocate_recognized_lot_book_cost(
            parked,
            disposal_date=date(2026, 6, 30),
            original_quantity=Decimal("100"),
            open_quantity_before=Decimal("100"),
            consumed_quantity=Decimal("10"),
            book_cost_fx_rate_to_base=Decimal("1"),
        )
