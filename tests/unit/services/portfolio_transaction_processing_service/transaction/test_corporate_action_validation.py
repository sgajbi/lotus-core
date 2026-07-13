"""Test service-owned corporate-action booking validation."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    corporate_action,
)


def _booked_transaction(transaction_type: str = "SPIN_OFF") -> BookedTransaction:
    return BookedTransaction(
        transaction_id="CA_BUNDLE_A_001",
        portfolio_id="PORT_001",
        instrument_id="SEC_001",
        security_id="SEC_001",
        transaction_date=datetime(2026, 3, 7, 10, 0, 0),
        transaction_type=transaction_type,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal(1),
        trade_currency="USD",
        currency="USD",
        parent_event_reference="CA-PARENT-001",
        economic_event_id="EVT-CA-001",
        linked_transaction_group_id="LTG-CA-001",
        source_instrument_id="SRC_001",
        target_instrument_id="TGT_001",
    )


def test_bundle_a_validation_accepts_normalized_spin_off() -> None:
    transaction = replace(_booked_transaction(), transaction_type=" spin_off ")

    assert corporate_action.is_bundle_a_corporate_action(transaction.transaction_type) is True
    assert corporate_action.validate_bundle_a_corporate_action(transaction) == ()


def test_bundle_a_validation_reports_required_linkage_and_instrument_fields() -> None:
    transaction = replace(
        _booked_transaction("DEMERGER_OUT"),
        parent_event_reference=None,
        economic_event_id=None,
        linked_transaction_group_id=None,
        source_instrument_id=None,
    )

    findings = corporate_action.validate_bundle_a_corporate_action(transaction)

    assert {finding.code for finding in findings} == {
        corporate_action.CorporateActionValidationReasonCode.MISSING_PARENT_EVENT_REFERENCE,
        corporate_action.CorporateActionValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
        corporate_action.CorporateActionValidationReasonCode.MISSING_SOURCE_INSTRUMENT_ID,
    }


def test_cash_consideration_requires_one_consistent_cash_leg_reference() -> None:
    missing = replace(
        _booked_transaction("CASH_CONSIDERATION"),
        linked_cash_transaction_id=None,
        external_cash_transaction_id=None,
    )
    mismatched = replace(
        missing,
        linked_cash_transaction_id="CASH_LEG_01",
        external_cash_transaction_id="CASH_LEG_02",
    )

    assert [
        finding.code for finding in corporate_action.validate_bundle_a_corporate_action(missing)
    ] == [corporate_action.CorporateActionValidationReasonCode.MISSING_CASH_CONSIDERATION_LINK]
    assert [
        finding.code for finding in corporate_action.validate_bundle_a_corporate_action(mismatched)
    ] == [corporate_action.CorporateActionValidationReasonCode.INCONSISTENT_CASH_CONSIDERATION_LINK]
