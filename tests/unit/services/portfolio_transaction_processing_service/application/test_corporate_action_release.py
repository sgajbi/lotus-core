"""Specify full source authority for corporate-action release generations."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionExecutionLeaseRequest,
    CorporateActionExecutionPlan,
    CorporateActionExecutionReleaseAuthority,
    build_corporate_action_execution_member_authority,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    build_transaction_semantic_identity,
)


def _transaction(transaction_id: str, *, epoch: int, quantity: str) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PB-CA-001",
        instrument_id=f"INST-{transaction_id}",
        security_id=f"SEC-{transaction_id}",
        transaction_date=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
        transaction_type="SPIN_OFF" if transaction_id.endswith("OUT") else "SPIN_IN",
        quantity=Decimal(quantity),
        price=Decimal("12.50"),
        gross_transaction_amount=Decimal("125.00"),
        trade_currency="SGD",
        currency="SGD",
        economic_event_id="CA-EVENT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        epoch=epoch,
    )


def _plan() -> CorporateActionExecutionPlan:
    return CorporateActionExecutionPlan(
        corporate_action_event_id="CA-EVENT-001",
        portfolio_id="PB-CA-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        manifest_content_hash=canonical_content_hash({"manifest": 1}),
        structural_plan_content_hash=canonical_content_hash({"structural-plan": 1}),
        readiness_state_version=7,
        through_observation_sequence=4,
        ordered_transaction_ids=("CA-OUT", "CA-IN"),
    )


def _release(*, target_quantity: str = "10") -> CorporateActionExecutionReleaseAuthority:
    transactions = (
        _transaction("CA-OUT", epoch=2, quantity="10"),
        _transaction("CA-IN", epoch=3, quantity=target_quantity),
    )
    members = tuple(
        build_corporate_action_execution_member_authority(
            execution_ordinal=ordinal,
            observation_id=101 + ordinal,
            observed_child_content_hash=canonical_content_hash(
                {"child": transaction.transaction_id, "epoch": transaction.epoch}
            ),
            transaction_epoch=transaction.epoch or 0,
            observed_transaction_payload_fingerprint=(
                build_transaction_semantic_identity(transaction).payload_fingerprint
            ),
            transaction=transaction,
        )
        for ordinal, transaction in enumerate(transactions)
    )
    return CorporateActionExecutionReleaseAuthority(plan=_plan(), members=members)


def test_release_authority_is_stable_and_changes_with_monetary_source_evidence() -> None:
    first = _release()
    replayed = _release()
    changed = _release(target_quantity="11")

    assert first.release_authority_hash == replayed.release_authority_hash
    assert first.release_authority_hash != changed.release_authority_hash
    assert len(first.release_authority_hash) == 64
    assert first.members[1].transaction_payload_fingerprint.startswith("sha256:")


def test_release_authority_rejects_order_or_observation_epoch_drift() -> None:
    release = _release()

    with pytest.raises(ValueError, match="exact structural execution order"):
        CorporateActionExecutionReleaseAuthority(
            plan=release.plan,
            members=tuple(reversed(release.members)),
        )

    transaction = _transaction("CA-OUT", epoch=2, quantity="10")
    with pytest.raises(ValueError, match="observation epoch"):
        build_corporate_action_execution_member_authority(
            execution_ordinal=0,
            observation_id=101,
            observed_child_content_hash=canonical_content_hash({"child": "CA-OUT"}),
            transaction_epoch=3,
            observed_transaction_payload_fingerprint="sha256:" + "b" * 64,
            transaction=transaction,
        )


def test_release_authority_rejects_noncontiguous_ordinals_and_duplicate_observations() -> None:
    release = _release()
    noncontiguous = replace(release.members[1], execution_ordinal=2)
    duplicate_observation = replace(
        release.members[1],
        observation_id=release.members[0].observation_id,
    )

    with pytest.raises(ValueError, match="contiguous"):
        CorporateActionExecutionReleaseAuthority(
            plan=release.plan,
            members=(release.members[0], noncontiguous),
        )
    with pytest.raises(ValueError, match="observation ids must be unique"):
        CorporateActionExecutionReleaseAuthority(
            plan=release.plan,
            members=(release.members[0], duplicate_observation),
        )


def test_execution_lease_request_requires_bounded_canonical_authority() -> None:
    lease = CorporateActionExecutionLeaseRequest(
        owner="transaction-worker-01",
        token="a" * 64,
        duration_seconds=300,
    )

    assert lease.owner == "transaction-worker-01"
    assert lease.duration_seconds == 300
    with pytest.raises(ValueError, match="between 1 and 3600"):
        CorporateActionExecutionLeaseRequest(
            owner="transaction-worker-01",
            token="a" * 64,
            duration_seconds=0,
        )
    with pytest.raises(ValueError, match="canonical sha256"):
        CorporateActionExecutionLeaseRequest(
            owner="transaction-worker-01",
            token="not-a-token",
            duration_seconds=300,
        )
