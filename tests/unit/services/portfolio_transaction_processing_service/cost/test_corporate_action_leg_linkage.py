"""Test deterministic reciprocal linkage for quantity-transfer corporate actions."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CorporateActionLegLinkageFinding,
    CorporateActionLegLinkageFindingType,
    reconcile_corporate_action_leg_linkage,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    instrument_id: str,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-LINKAGE-01",
        instrument_id=instrument_id,
        security_id=instrument_id,
        transaction_date=datetime(2026, 8, 4, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal(10),
        price=Decimal(1),
        gross_transaction_amount=Decimal(10),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="GROUP-LINKAGE-01",
        parent_event_reference="PARENT-LINKAGE-01",
    )


def _reciprocal_pair(
    *, source_type: str = "EXCHANGE_OUT", target_type: str = "EXCHANGE_IN"
) -> tuple[BookedTransaction, BookedTransaction]:
    source = replace(
        _transaction(
            transaction_id="SOURCE-OUT-01",
            transaction_type=source_type,
            instrument_id="SOURCE-INSTRUMENT-01",
        ),
        source_instrument_id="SOURCE-INSTRUMENT-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
        target_transaction_reference="TARGET-IN-01",
    )
    target = replace(
        _transaction(
            transaction_id="TARGET-IN-01",
            transaction_type=target_type,
            instrument_id="TARGET-INSTRUMENT-01",
        ),
        source_instrument_id="SOURCE-INSTRUMENT-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
        source_transaction_reference="SOURCE-OUT-01",
    )
    return source, target


@pytest.mark.parametrize(
    ("source_type", "target_type"),
    (
        ("MERGER_OUT", "MERGER_IN"),
        ("EXCHANGE_OUT", "EXCHANGE_IN"),
        ("REPLACEMENT_OUT", "REPLACEMENT_IN"),
    ),
)
def test_reciprocal_quantity_transfer_pair_is_balanced(
    source_type: str,
    target_type: str,
) -> None:
    source, target = _reciprocal_pair(source_type=source_type, target_type=target_type)

    assert reconcile_corporate_action_leg_linkage((target, source)) == ()


def test_source_without_persisted_target_is_reported() -> None:
    source, _target = _reciprocal_pair()

    findings = reconcile_corporate_action_leg_linkage((source,))

    assert len(findings) == 1
    assert findings[0].finding_type == "missing_reciprocal_leg"
    assert findings[0].source_transaction_id == "SOURCE-OUT-01"
    assert findings[0].target_transaction_id == "TARGET-IN-01"


def test_target_without_persisted_source_is_reported() -> None:
    _source, target = _reciprocal_pair()

    findings = reconcile_corporate_action_leg_linkage((target,))

    assert findings == (
        CorporateActionLegLinkageFinding(
            finding_type=CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG,
            source_transaction_id="SOURCE-OUT-01",
            target_transaction_id="TARGET-IN-01",
            field="target_transaction_reference",
            expected_value="TARGET-IN-01",
            observed_value=None,
        ),
    )


def test_duplicate_target_identity_does_not_select_an_arbitrary_reciprocal_leg() -> None:
    source, target = _reciprocal_pair()
    conflicting_target = replace(target, source_transaction_reference="OTHER-SOURCE")

    findings = reconcile_corporate_action_leg_linkage((source, target, conflicting_target))

    assert findings == (
        CorporateActionLegLinkageFinding(
            finding_type=CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG,
            source_transaction_id="SOURCE-OUT-01",
            target_transaction_id="TARGET-IN-01",
            field="target_transaction_reference",
            expected_value="TARGET-IN-01",
            observed_value=None,
        ),
    )


def test_wrong_target_family_and_non_reciprocal_reference_are_both_reported() -> None:
    source, target = _reciprocal_pair(target_type="MERGER_IN")
    target = replace(target, source_transaction_reference="OTHER-SOURCE")

    findings = reconcile_corporate_action_leg_linkage((source, target))

    assert [finding.finding_type for finding in findings] == [
        CorporateActionLegLinkageFindingType.UNEXPECTED_RECIPROCAL_TYPE,
        CorporateActionLegLinkageFindingType.TRANSACTION_REFERENCE_MISMATCH,
        CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG,
    ]
    assert reconcile_corporate_action_leg_linkage((target, source)) == tuple(findings)


@pytest.mark.parametrize(
    ("leg", "field", "value"),
    (
        ("source", "source_instrument_id", "WRONG-SOURCE"),
        ("source", "target_instrument_id", "WRONG-TARGET"),
        ("target", "source_instrument_id", "WRONG-SOURCE"),
        ("target", "target_instrument_id", "WRONG-TARGET"),
    ),
)
def test_instrument_identity_mismatch_fails_closed(
    leg: str,
    field: str,
    value: str,
) -> None:
    source, target = _reciprocal_pair()
    if leg == "source":
        source = replace(source, **{field: value})
    else:
        target = replace(target, **{field: value})

    findings = reconcile_corporate_action_leg_linkage((source, target))

    assert len(findings) == 1
    assert findings[0].finding_type == "instrument_reference_mismatch"
    assert findings[0].field == field


def test_bundle_a_and_unrelated_transactions_do_not_create_quantity_linkage_findings() -> None:
    demerger = _transaction(
        transaction_id="DEMERGER-OUT-01",
        transaction_type="DEMERGER_OUT",
        instrument_id="SOURCE-INSTRUMENT-01",
    )
    buy = _transaction(
        transaction_id="BUY-01",
        transaction_type="BUY",
        instrument_id="SOURCE-INSTRUMENT-01",
    )

    assert reconcile_corporate_action_leg_linkage((demerger, buy)) == ()
