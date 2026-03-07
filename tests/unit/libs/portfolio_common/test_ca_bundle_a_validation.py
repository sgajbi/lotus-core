from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    CaBundleAValidationReasonCode,
    validate_ca_bundle_a_transaction,
)


def _base_event(transaction_type: str = "SPIN_OFF") -> TransactionEvent:
    return TransactionEvent(
        transaction_id="CA_BUNDLE_A_001",
        portfolio_id="PORT_001",
        instrument_id="SEC_001",
        security_id="SEC_001",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
        parent_event_reference="CA-PARENT-001",
        economic_event_id="EVT-CA-001",
        linked_transaction_group_id="LTG-CA-001",
        source_instrument_id="SRC_001",
        target_instrument_id="TGT_001",
    )


def test_validate_ca_bundle_a_happy_path_spin_off() -> None:
    issues = validate_ca_bundle_a_transaction(_base_event("SPIN_OFF"))
    assert issues == []


def test_validate_ca_bundle_a_requires_parent_event_reference() -> None:
    event = _base_event("SPIN_IN").model_copy(update={"parent_event_reference": None})
    issues = validate_ca_bundle_a_transaction(event)
    assert any(
        i.code == CaBundleAValidationReasonCode.MISSING_PARENT_EVENT_REFERENCE for i in issues
    )


def test_validate_ca_bundle_a_requires_source_instrument_for_out_type() -> None:
    event = _base_event("DEMERGER_OUT").model_copy(update={"source_instrument_id": None})
    issues = validate_ca_bundle_a_transaction(event)
    assert any(i.code == CaBundleAValidationReasonCode.MISSING_SOURCE_INSTRUMENT_ID for i in issues)


def test_validate_ca_bundle_a_requires_target_instrument_for_in_type() -> None:
    event = _base_event("SPIN_IN").model_copy(update={"target_instrument_id": None})
    issues = validate_ca_bundle_a_transaction(event)
    assert any(i.code == CaBundleAValidationReasonCode.MISSING_TARGET_INSTRUMENT_ID for i in issues)


def test_validate_ca_bundle_a_cash_consideration_requires_cash_link() -> None:
    event = _base_event("CASH_CONSIDERATION").model_copy(
        update={
            "linked_cash_transaction_id": None,
            "external_cash_transaction_id": None,
        }
    )
    issues = validate_ca_bundle_a_transaction(event)
    assert any(
        i.code == CaBundleAValidationReasonCode.MISSING_CASH_CONSIDERATION_LINK for i in issues
    )


def test_validate_ca_bundle_a_cash_consideration_rejects_link_mismatch() -> None:
    event = _base_event("CASH_CONSIDERATION").model_copy(
        update={
            "linked_cash_transaction_id": "CASH_LEG_01",
            "external_cash_transaction_id": "CASH_LEG_02",
        }
    )
    issues = validate_ca_bundle_a_transaction(event)
    assert any(
        i.code == CaBundleAValidationReasonCode.INCONSISTENT_CASH_CONSIDERATION_LINK
        for i in issues
    )
