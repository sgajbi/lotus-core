from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    evaluate_ca_bundle_a_reconciliation,
    find_missing_ca_bundle_a_dependencies,
)


def _event(
    *,
    transaction_id: str,
    transaction_type: str,
    gross_transaction_amount: str,
    net_cost_local: str | None = None,
    dependency_reference_ids: list[str] | None = None,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id="PORT_001",
        instrument_id="SEC_001",
        security_id="SEC_001",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal(gross_transaction_amount),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-001",
        parent_event_reference="CA-PARENT-001",
        net_cost_local=Decimal(net_cost_local) if net_cost_local is not None else None,
        dependency_reference_ids=dependency_reference_ids,
    )


def test_bundle_a_reconciliation_balanced_when_target_in_equals_source_out() -> None:
    events = [
        _event(
            transaction_id="SRC_01",
            transaction_type="SPIN_OFF",
            gross_transaction_amount="100",
            net_cost_local="-100",
        ),
        _event(
            transaction_id="TGT_01",
            transaction_type="SPIN_IN",
            gross_transaction_amount="100",
            net_cost_local="100",
        ),
    ]
    result = evaluate_ca_bundle_a_reconciliation(events)
    assert result.status == "balanced"
    assert result.net_basis_delta_local == Decimal("0")


def test_bundle_a_reconciliation_detects_basis_mismatch() -> None:
    events = [
        _event(
            transaction_id="SRC_01",
            transaction_type="DEMERGER_OUT",
            gross_transaction_amount="100",
            net_cost_local="-100",
        ),
        _event(
            transaction_id="TGT_01",
            transaction_type="DEMERGER_IN",
            gross_transaction_amount="60",
            net_cost_local="60",
        ),
    ]
    result = evaluate_ca_bundle_a_reconciliation(events)
    assert result.status == "basis_mismatch"
    assert result.net_basis_delta_local == Decimal("-40")


def test_bundle_a_reconciliation_reports_insufficient_legs() -> None:
    result = evaluate_ca_bundle_a_reconciliation(
        [
            _event(
                transaction_id="SRC_01",
                transaction_type="SPIN_OFF",
                gross_transaction_amount="100",
                net_cost_local="-100",
            )
        ]
    )
    assert result.status == "insufficient_legs"


def test_bundle_a_reconciliation_dependency_gap_detection() -> None:
    event = _event(
        transaction_id="TGT_01",
        transaction_type="DEMERGER_IN",
        gross_transaction_amount="100",
        dependency_reference_ids=["SRC_01", "TGT_00"],
    )
    missing = find_missing_ca_bundle_a_dependencies(event, {"SRC_01"})
    assert missing == ["TGT_00"]
