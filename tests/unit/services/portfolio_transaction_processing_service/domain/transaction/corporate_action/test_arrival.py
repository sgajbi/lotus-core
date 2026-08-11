"""Specify fail-closed recognition of manifest-governed child arrivals."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    IncompleteCorporateActionManifestIdentityError,
    corporate_action_manifest_child,
)


def _transaction(**overrides: object) -> BookedTransaction:
    values: dict[str, object] = {
        "transaction_id": "CA-OUT-001",
        "portfolio_id": "PB-CA-001",
        "instrument_id": "INST-OLD",
        "security_id": "SEC-OLD",
        "transaction_date": datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
        "transaction_type": "SPIN_OFF",
        "quantity": Decimal("10"),
        "price": Decimal("12.50"),
        "gross_transaction_amount": Decimal("125.00"),
        "trade_currency": "SGD",
        "currency": "SGD",
        "economic_event_id": "CA-EVENT-001",
        "linked_transaction_group_id": "CA-GROUP-001",
        "parent_event_reference": "CA-PARENT-001",
        "child_role": "SOURCE_POSITION_CLOSE",
        "child_sequence_hint": 1,
        "dependency_reference_ids": ("CA-PREREQUISITE-001",),
        "source_instrument_id": "INST-OLD",
        "target_instrument_id": "INST-NEW",
    }
    values.update(overrides)
    return BookedTransaction(**values)  # type: ignore[arg-type]


def test_fully_identified_governed_child_maps_source_graph_authority() -> None:
    child = corporate_action_manifest_child(_transaction())

    assert child is not None
    assert child.transaction_id == "CA-OUT-001"
    assert child.transaction_type == "SPIN_OFF"
    assert child.child_role == "SOURCE_POSITION_CLOSE"
    assert child.dependency_transaction_ids == ("CA-PREREQUISITE-001",)
    assert child.source_instrument_id == "INST-OLD"
    assert child.target_instrument_id == "INST-NEW"


@pytest.mark.parametrize(
    "missing_field",
    (
        "economic_event_id",
        "linked_transaction_group_id",
        "parent_event_reference",
        "child_role",
    ),
)
def test_partial_graph_identity_fails_closed(missing_field: str) -> None:
    transaction = replace(_transaction(), **{missing_field: None})

    with pytest.raises(IncompleteCorporateActionManifestIdentityError, match="fully populated"):
        corporate_action_manifest_child(transaction)


def test_absent_graph_identity_preserves_ordinary_compatibility_path() -> None:
    transaction = replace(
        _transaction(),
        economic_event_id=None,
        linked_transaction_group_id=None,
        parent_event_reference=None,
        child_role=None,
    )

    assert corporate_action_manifest_child(transaction) is None


@pytest.mark.parametrize("transaction_type", ("BUY", "SELL", "DIVIDEND", "INTEREST"))
def test_non_corporate_action_type_remains_on_ordinary_processing_path(
    transaction_type: str,
) -> None:
    assert corporate_action_manifest_child(_transaction(transaction_type=transaction_type)) is None


@pytest.mark.parametrize("transaction_type", ("ADJUSTMENT", "FEE", "TAX"))
def test_ordinary_charge_or_adjustment_with_shared_linkage_is_not_parked(
    transaction_type: str,
) -> None:
    assert (
        corporate_action_manifest_child(
            _transaction(
                transaction_type=transaction_type,
                parent_event_reference=None,
                child_role=None,
            )
        )
        is None
    )


@pytest.mark.parametrize("manifest_field", ("parent_event_reference", "child_role"))
def test_manifest_specific_identity_still_requires_complete_authority(
    manifest_field: str,
) -> None:
    identity = {
        "parent_event_reference": None,
        "child_role": None,
    }
    identity[manifest_field] = "MANIFEST-IDENTITY"
    transaction = replace(
        _transaction(),
        **identity,
    )

    with pytest.raises(IncompleteCorporateActionManifestIdentityError, match="fully populated"):
        corporate_action_manifest_child(transaction)


def test_non_domain_value_is_rejected() -> None:
    with pytest.raises(TypeError, match="BookedTransaction"):
        corporate_action_manifest_child(object())  # type: ignore[arg-type]
