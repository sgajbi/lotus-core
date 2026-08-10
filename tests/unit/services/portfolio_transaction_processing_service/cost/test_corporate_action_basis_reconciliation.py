"""Test service-owned corporate-action basis reconciliation."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    reconcile_corporate_action_basis,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)


def _booked_transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    gross_amount: str,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT_001",
        instrument_id="SEC_001",
        security_id="SEC_001",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal(gross_amount),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-001",
        parent_event_reference="CA-PARENT-001",
    )


def test_corporate_action_basis_reconciliation_balances_source_target_and_cash() -> None:
    transactions = (
        replace(
            _booked_transaction(
                transaction_id="SRC_01",
                transaction_type="DEMERGER_OUT",
                gross_amount="300",
            ),
            net_cost_local=Decimal("-300"),
        ),
        replace(
            _booked_transaction(
                transaction_id="TGT_01",
                transaction_type="DEMERGER_IN",
                gross_amount="250",
            ),
            net_cost_local=Decimal("250"),
        ),
        replace(
            _booked_transaction(
                transaction_id="CASH_01",
                transaction_type="CASH_CONSIDERATION",
                gross_amount="50",
            ),
            allocated_cost_basis_local=Decimal("50"),
        ),
    )

    result = reconcile_corporate_action_basis(transactions)

    assert result.status == "balanced"
    assert result.source_basis_out_local == Decimal("300")
    assert result.target_basis_in_local == Decimal("250")
    assert result.cash_basis_local == Decimal("50")
    assert result.cash_consideration_basis_local == Decimal("50")
    assert result.fractional_basis_local == Decimal(0)
    assert result.net_basis_delta_local == Decimal(0)


def test_corporate_action_basis_reconciliation_balances_multi_target_fractional_basis() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01", transaction_type="DEMERGER_OUT", gross_amount="100"
        ),
        net_cost_local=Decimal("-100"),
    )
    target_basis_values = (Decimal("30"), Decimal("30"), Decimal("40"))
    targets = tuple(
        replace(
            _booked_transaction(
                transaction_id=f"TGT_{ordinal:02d}",
                transaction_type="DEMERGER_IN",
                gross_amount=str(target_basis),
            ),
            net_cost_local=target_basis,
        )
        for ordinal, target_basis in enumerate(target_basis_values, start=1)
    )
    fractional = replace(
        _booked_transaction(
            transaction_id="CIL_01", transaction_type="CASH_IN_LIEU", gross_amount="12"
        ),
        quantity=Decimal("0.1"),
        allocated_cost_basis_local=Decimal("10"),
    )
    generated_cash = replace(
        _booked_transaction(
            transaction_id="ADJ_CIL_01", transaction_type="ADJUSTMENT", gross_amount="12"
        ),
        movement_direction="INFLOW",
        originating_transaction_type="CASH_IN_LIEU",
        adjustment_reason="CASH_IN_LIEU_SETTLEMENT",
        net_cost_local=Decimal("12"),
    )

    result = reconcile_corporate_action_basis((source, *targets, fractional, generated_cash))

    assert result.status == "balanced"
    assert result.target_leg_count == 3
    assert result.fractional_cash_leg_count == 1
    assert result.fractional_basis_local == Decimal("10")
    assert result.target_basis_retained_local == Decimal("90")
    assert result.cash_consideration_basis_local == Decimal(0)
    assert result.cash_basis_local == Decimal("10")
    assert result.excluded_cash_settlement_adjustment_count == 1
    assert result.unsupported_adjustment_count == 0
    assert result.net_basis_delta_local == Decimal(0)


def test_corporate_action_basis_reconciliation_fails_closed_for_ambiguous_adjustment() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01", transaction_type="SPIN_OFF", gross_amount="100"
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01", transaction_type="SPIN_IN", gross_amount="100"
        ),
        net_cost_local=Decimal("100"),
    )
    ambiguous_adjustment = replace(
        _booked_transaction(
            transaction_id="ADJ_01", transaction_type="ADJUSTMENT", gross_amount="5"
        ),
        movement_direction="INFLOW",
        adjustment_reason="MANUAL_BASIS_OVERRIDE",
    )

    result = reconcile_corporate_action_basis((source, target, ambiguous_adjustment))

    assert result.status == "unsupported_adjustment"
    assert result.unsupported_adjustment_count == 1
    assert result.excluded_cash_settlement_adjustment_count == 0


@pytest.mark.parametrize(
    ("originating_transaction_type", "adjustment_reason", "expected_excluded"),
    [
        ("CASH_IN_LIEU", "CASH_IN_LIEU_SETTLEMENT", True),
        ("CASH_CONSIDERATION", "CASH_CONSIDERATION_SETTLEMENT", True),
        ("CASH_IN_LIEU", "CASH_CONSIDERATION_SETTLEMENT", False),
        ("CASH_CONSIDERATION", "CASH_IN_LIEU_SETTLEMENT", False),
    ],
)
def test_corporate_action_basis_reconciliation_requires_exact_settlement_identity(
    originating_transaction_type: str,
    adjustment_reason: str,
    expected_excluded: bool,
) -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01", transaction_type="SPIN_OFF", gross_amount="100"
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01", transaction_type="SPIN_IN", gross_amount="100"
        ),
        net_cost_local=Decimal("100"),
    )
    adjustment = replace(
        _booked_transaction(
            transaction_id="ADJ_01", transaction_type="ADJUSTMENT", gross_amount="5"
        ),
        movement_direction="INFLOW",
        originating_transaction_type=originating_transaction_type,
        adjustment_reason=adjustment_reason,
    )

    result = reconcile_corporate_action_basis((source, target, adjustment))

    assert result.status == ("balanced" if expected_excluded else "unsupported_adjustment")
    assert result.unsupported_adjustment_count == (0 if expected_excluded else 1)
    assert result.excluded_cash_settlement_adjustment_count == (1 if expected_excluded else 0)


def test_corporate_action_basis_reconciliation_rejects_negative_retained_target_basis() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01", transaction_type="DEMERGER_OUT", gross_amount="100"
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01", transaction_type="DEMERGER_IN", gross_amount="100"
        ),
        net_cost_local=Decimal("100"),
    )
    fractional = replace(
        _booked_transaction(
            transaction_id="CIL_01", transaction_type="CASH_IN_LIEU", gross_amount="110"
        ),
        allocated_cost_basis_local=Decimal("110"),
    )

    result = reconcile_corporate_action_basis((source, target, fractional))

    assert result.status == "invalid_basis_allocation"
    assert result.target_basis_retained_local == Decimal("-10")
    assert result.net_basis_delta_local == Decimal(0)


def test_corporate_action_basis_reconciliation_distinguishes_incomplete_evidence() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="SPIN_OFF",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="SPIN_IN",
            gross_amount="100",
        ),
        net_cost_local=Decimal("100"),
    )
    cash_without_basis = _booked_transaction(
        transaction_id="CASH_01",
        transaction_type="CASH_CONSIDERATION",
        gross_amount="25",
    )

    assert reconcile_corporate_action_basis((source,)).status == "insufficient_legs"
    result = reconcile_corporate_action_basis((source, target, cash_without_basis))
    assert result.status == "insufficient_cash_basis"
    assert result.missing_cash_basis_count == 1


def test_corporate_action_basis_reconciliation_reports_basis_mismatch() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="DEMERGER_OUT",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_amount="60",
        ),
        net_cost_local=Decimal("60"),
    )

    result = reconcile_corporate_action_basis((source, target))

    assert result.status == "basis_mismatch"
    assert result.net_basis_delta_local == Decimal("-40")


@pytest.mark.parametrize(
    ("target_basis", "expected_status"),
    (
        ("100.00", "balanced"),
        ("99.99", "balanced"),
        ("99.989", "basis_mismatch"),
        ("100.011", "basis_mismatch"),
    ),
)
def test_corporate_action_basis_reconciliation_enforces_tolerance_boundary(
    target_basis: str,
    expected_status: str,
) -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="SPIN_OFF",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="SPIN_IN",
            gross_amount=target_basis,
        ),
        net_cost_local=Decimal(target_basis),
    )

    assert reconcile_corporate_action_basis((source, target)).status == expected_status


def test_corporate_action_basis_reconciliation_conserves_multi_target_allocation() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="DEMERGER_OUT",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target_one = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_amount="30",
        ),
        net_cost_local=Decimal("30"),
    )
    target_two = replace(
        _booked_transaction(
            transaction_id="TGT_02",
            transaction_type="DEMERGER_IN",
            gross_amount="70",
        ),
        net_cost_local=Decimal("70"),
    )

    result = reconcile_corporate_action_basis((source, target_one, target_two))

    assert result.status == "balanced"
    assert result.target_leg_count == 2
    assert result.target_basis_in_local == Decimal("100")


def test_corporate_action_basis_reconciliation_treats_zero_cash_basis_as_evidence() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="DEMERGER_OUT",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_amount="100",
        ),
        net_cost_local=Decimal("100"),
    )
    cash = replace(
        _booked_transaction(
            transaction_id="CASH_01",
            transaction_type="CASH_CONSIDERATION",
            gross_amount="0",
        ),
        allocated_cost_basis_local=Decimal(0),
    )

    result = reconcile_corporate_action_basis((source, target, cash))

    assert result.status == "balanced"
    assert result.missing_cash_basis_count == 0


def test_corporate_action_basis_reconciliation_rejects_negative_cash_basis() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01",
            transaction_type="DEMERGER_OUT",
            gross_amount="100",
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_amount="100",
        ),
        net_cost_local=Decimal("100"),
    )
    cash = replace(
        _booked_transaction(
            transaction_id="CASH_01",
            transaction_type="CASH_CONSIDERATION",
            gross_amount="5",
        ),
        allocated_cost_basis_local=Decimal("-5"),
    )

    result = reconcile_corporate_action_basis((source, target, cash))

    assert result.status == "insufficient_cash_basis"
    assert result.missing_cash_basis_count == 1


def test_corporate_action_basis_reconciliation_uses_gross_basis_when_cost_is_unavailable() -> None:
    source = _booked_transaction(
        transaction_id="SRC_01",
        transaction_type="SPIN_OFF",
        gross_amount="100",
    )
    target = _booked_transaction(
        transaction_id="TGT_01",
        transaction_type="SPIN_IN",
        gross_amount="100",
    )

    result = reconcile_corporate_action_basis((source, target))

    assert result.status == "balanced"
    assert result.source_basis_out_local == Decimal("100")
    assert result.target_basis_in_local == Decimal("100")


def test_corporate_action_dependency_references_preserve_order() -> None:
    from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
        missing_corporate_action_dependencies,
    )

    transaction = replace(
        _booked_transaction(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_amount="100",
        ),
        dependency_reference_ids=("SRC_01", "TGT_00"),
    )

    assert missing_corporate_action_dependencies(transaction, {"SRC_01"}) == ("TGT_00",)


@settings(max_examples=100, deadline=None)
@given(
    target_basis_values=st.lists(
        st.integers(min_value=1, max_value=1_000), min_size=1, max_size=20
    ),
    fractional_basis_value=st.integers(min_value=0, max_value=1_000),
)
def test_corporate_action_conservation_is_order_independent_for_generated_allocations(
    target_basis_values: list[int],
    fractional_basis_value: int,
) -> None:
    source_basis = sum(target_basis_values)
    governed_fractional_basis = fractional_basis_value % (source_basis + 1)
    source = replace(
        _booked_transaction(
            transaction_id="SRC_PROPERTY",
            transaction_type="SPIN_OFF",
            gross_amount=str(source_basis),
        ),
        net_cost_local=Decimal(-source_basis),
    )
    targets = tuple(
        replace(
            _booked_transaction(
                transaction_id=f"TGT_PROPERTY_{ordinal:02d}",
                transaction_type="SPIN_IN",
                gross_amount=str(basis),
            ),
            net_cost_local=Decimal(basis),
        )
        for ordinal, basis in enumerate(target_basis_values)
    )
    fractional = replace(
        _booked_transaction(
            transaction_id="CIL_PROPERTY",
            transaction_type="CASH_IN_LIEU",
            gross_amount=str(governed_fractional_basis),
        ),
        allocated_cost_basis_local=Decimal(governed_fractional_basis),
    )

    forward = reconcile_corporate_action_basis((source, *targets, fractional))
    reversed_result = reconcile_corporate_action_basis(
        tuple(reversed((source, *targets, fractional)))
    )

    assert forward == reversed_result
    assert forward.status == "balanced"
    assert forward.source_basis_out_local == Decimal(source_basis)
    assert forward.target_basis_in_local == sum(map(Decimal, target_basis_values))
    assert forward.target_basis_retained_local == Decimal(source_basis - governed_fractional_basis)
    assert forward.fractional_basis_local == Decimal(governed_fractional_basis)
    assert forward.net_basis_delta_local == 0
