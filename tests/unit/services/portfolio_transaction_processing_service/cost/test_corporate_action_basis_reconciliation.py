"""Test service-owned corporate-action basis reconciliation."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

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
