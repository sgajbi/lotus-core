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


def _upstream_settlement_pair(
    *,
    transaction_id: str,
    transaction_type: str,
    gross_amount: str = "5",
) -> tuple[BookedTransaction, BookedTransaction]:
    cash_leg_id = f"{transaction_id}-SETTLEMENT"
    adjustment_reason = f"{transaction_type}_SETTLEMENT"
    origin = replace(
        _booked_transaction(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            gross_amount=gross_amount,
        ),
        allocated_cost_basis_local=Decimal(0),
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=cash_leg_id,
        economic_event_id="EVENT_001",
    )
    cash_leg = replace(
        _booked_transaction(
            transaction_id=cash_leg_id,
            transaction_type="ADJUSTMENT",
            gross_amount=gross_amount,
        ),
        economic_event_id=origin.economic_event_id,
        originating_transaction_id=origin.transaction_id,
        originating_transaction_type=transaction_type,
        adjustment_reason=adjustment_reason,
        link_type=f"{transaction_type}_TO_CASH",
    )
    return origin, cash_leg


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
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="CIL_01-SETTLEMENT",
        economic_event_id="EVENT_001",
    )
    generated_cash = replace(
        _booked_transaction(
            transaction_id="CIL_01-SETTLEMENT",
            transaction_type="ADJUSTMENT",
            gross_amount="12",
        ),
        economic_event_id=fractional.economic_event_id,
        movement_direction="INFLOW",
        originating_transaction_id=fractional.transaction_id,
        originating_transaction_type="CASH_IN_LIEU",
        adjustment_reason="CASH_IN_LIEU_SETTLEMENT",
        link_type="CASH_IN_LIEU_TO_CASH",
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
    originating_transaction, canonical_adjustment = _upstream_settlement_pair(
        transaction_id="ORIGIN_01",
        transaction_type=originating_transaction_type,
    )
    adjustment = replace(
        canonical_adjustment,
        adjustment_reason=adjustment_reason,
    )

    result = reconcile_corporate_action_basis((source, target, originating_transaction, adjustment))

    assert result.status == ("balanced" if expected_excluded else "unsupported_adjustment")
    assert result.unsupported_adjustment_count == (0 if expected_excluded else 1)
    assert result.excluded_cash_settlement_adjustment_count == (1 if expected_excluded else 0)


@pytest.mark.parametrize(
    ("originating_transaction_id", "link_type", "origin_transaction_type"),
    [
        (None, "CASH_IN_LIEU_TO_CASH", "CASH_IN_LIEU"),
        ("CIL_01", None, "CASH_IN_LIEU"),
        ("CIL_01", "CASH_CONSIDERATION_TO_CASH", "CASH_IN_LIEU"),
        ("OUTSIDE_COHORT", "CASH_IN_LIEU_TO_CASH", "CASH_IN_LIEU"),
        ("CIL_01", "CASH_IN_LIEU_TO_CASH", "CASH_CONSIDERATION"),
    ],
)
def test_corporate_action_basis_reconciliation_requires_reciprocal_cohort_linkage(
    originating_transaction_id: str | None,
    link_type: str | None,
    origin_transaction_type: str,
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
    origin, canonical_adjustment = _upstream_settlement_pair(
        transaction_id="CIL_01",
        transaction_type="CASH_IN_LIEU",
    )
    origin = replace(origin, transaction_type=origin_transaction_type)
    adjustment = replace(
        canonical_adjustment,
        originating_transaction_id=originating_transaction_id,
        link_type=link_type,
    )

    result = reconcile_corporate_action_basis((source, target, origin, adjustment))

    assert result.status == "unsupported_adjustment"
    assert result.unsupported_adjustment_count == 1
    assert result.excluded_cash_settlement_adjustment_count == 0


def test_corporate_action_basis_reconciliation_rejects_ambiguous_origin_identity() -> None:
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
    origin, adjustment = _upstream_settlement_pair(
        transaction_id="CIL_01",
        transaction_type="CASH_IN_LIEU",
    )

    result = reconcile_corporate_action_basis((source, target, origin, replace(origin), adjustment))

    assert result.status == "unsupported_adjustment"
    assert result.unsupported_adjustment_count == 1
    assert result.excluded_cash_settlement_adjustment_count == 0


@pytest.mark.parametrize(
    ("adjustment_changes", "origin_changes"),
    [
        ({"transaction_id": "SOURCE_ADJUSTMENT_01"}, {}),
        ({"portfolio_id": "OTHER_PORTFOLIO"}, {}),
        ({"economic_event_id": "OTHER_EVENT"}, {}),
        ({"linked_transaction_group_id": "OTHER_GROUP"}, {}),
        ({}, {"cash_entry_mode": None}),
        ({}, {"cash_entry_mode": "AUTO_GENERATE"}),
        ({}, {"external_cash_transaction_id": None}),
        ({}, {"external_cash_transaction_id": "OTHER_CASH_LEG"}),
    ],
)
def test_corporate_action_basis_reconciliation_rejects_upstream_pair_masquerades(
    adjustment_changes: dict[str, object],
    origin_changes: dict[str, object],
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
    origin, adjustment = _upstream_settlement_pair(
        transaction_id="CIL_01",
        transaction_type="CASH_IN_LIEU",
    )

    result = reconcile_corporate_action_basis(
        (
            source,
            target,
            replace(origin, **origin_changes),
            replace(adjustment, **adjustment_changes),
        )
    )

    assert result.status == "unsupported_adjustment"
    assert result.unsupported_adjustment_count == 1
    assert result.excluded_cash_settlement_adjustment_count == 0


def test_corporate_action_basis_reconciliation_accepts_governed_upstream_cash_pair() -> None:
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
    origin, cash_leg = _upstream_settlement_pair(
        transaction_id="CIL_01",
        transaction_type="CASH_IN_LIEU",
    )

    result = reconcile_corporate_action_basis((source, target, origin, cash_leg))

    assert result.status == "balanced"
    assert result.excluded_cash_settlement_adjustment_count == 1
    assert result.unsupported_adjustment_count == 0


def test_corporate_action_basis_reconciliation_indexes_large_cohort_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
        corporate_action_reconciliation as reconciliation_module,
    )

    normalization_calls = 0
    canonical_normalizer = reconciliation_module.normalize_corporate_action_transaction_type

    def counting_normalizer(value: str | None) -> str:
        nonlocal normalization_calls
        normalization_calls += 1
        return canonical_normalizer(value)

    monkeypatch.setattr(
        reconciliation_module,
        "normalize_corporate_action_transaction_type",
        counting_normalizer,
    )
    source = replace(
        _booked_transaction(
            transaction_id="SRC_SCALE", transaction_type="SPIN_OFF", gross_amount="100"
        ),
        net_cost_local=Decimal("-100"),
    )
    target = replace(
        _booked_transaction(
            transaction_id="TGT_SCALE", transaction_type="SPIN_IN", gross_amount="100"
        ),
        net_cost_local=Decimal("100"),
    )
    unrelated = tuple(
        _booked_transaction(
            transaction_id=f"UNRELATED_{index:04d}",
            transaction_type="BUY",
            gross_amount="0",
        )
        for index in range(1_000)
    )
    cohort = (source, target, *unrelated)

    result = reconcile_corporate_action_basis(iter(cohort))

    assert result.status == "balanced"
    assert normalization_calls == len(cohort)


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


def test_reconciliation_rejects_hidden_negative_basis_using_cash_leg_instrument() -> None:
    source = replace(
        _booked_transaction(
            transaction_id="SRC_01", transaction_type="DEMERGER_OUT", gross_amount="110"
        ),
        net_cost_local=Decimal("-110"),
    )
    target_a = replace(
        _booked_transaction(
            transaction_id="TGT_A", transaction_type="DEMERGER_IN", gross_amount="10"
        ),
        instrument_id="SEC_A",
        security_id="SEC_A",
        net_cost_local=Decimal("10"),
    )
    target_b = replace(
        _booked_transaction(
            transaction_id="TGT_B", transaction_type="DEMERGER_IN", gross_amount="100"
        ),
        instrument_id="SEC_B",
        security_id="SEC_B",
        net_cost_local=Decimal("100"),
    )
    fractional = replace(
        _booked_transaction(
            transaction_id="CIL_A", transaction_type="CASH_IN_LIEU", gross_amount="20"
        ),
        instrument_id="SEC_A",
        security_id="SEC_A",
        target_instrument_id="SEC_B",
        allocated_cost_basis_local=Decimal("20"),
    )

    result = reconcile_corporate_action_basis((source, target_a, target_b, fractional))

    assert result.status == "invalid_basis_allocation"
    assert result.target_basis_in_local == Decimal("110")
    assert result.target_basis_retained_local == Decimal("90")
    assert result.fractional_basis_local == Decimal("20")
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
