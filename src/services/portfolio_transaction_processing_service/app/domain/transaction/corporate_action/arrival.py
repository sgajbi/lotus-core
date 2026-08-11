"""Recognize source transactions that opt in to parent-manifest execution."""

from __future__ import annotations

from ..booked import BookedTransaction
from .classification import is_manifest_governed_corporate_action
from .event_graph import CorporateActionEventChild


class IncompleteCorporateActionManifestIdentityError(ValueError):
    """Raised when a governed child partially claims parent-manifest identity."""


def corporate_action_manifest_child(
    transaction: BookedTransaction,
) -> CorporateActionEventChild | None:
    """Map a fully identified governed child, leaving ordinary transactions untouched.

    Transaction type alone is never sufficient authority. The source must provide the
    event, cohort, parent, and role identities required to match an immutable manifest.
    """

    if not isinstance(transaction, BookedTransaction):
        raise TypeError("transaction must be a BookedTransaction")
    if not is_manifest_governed_corporate_action(transaction.transaction_type):
        return None
    identity_values = (
        transaction.economic_event_id,
        transaction.linked_transaction_group_id,
        transaction.parent_event_reference,
        transaction.child_role,
    )
    populated_identity_count = sum(_present(value) for value in identity_values)
    if populated_identity_count == 0:
        return None
    if populated_identity_count != len(identity_values):
        raise IncompleteCorporateActionManifestIdentityError(
            "manifest-governed corporate-action identity must be fully populated"
        )
    return CorporateActionEventChild(
        transaction_id=transaction.transaction_id,
        transaction_type=transaction.transaction_type,
        child_role=str(transaction.child_role),
        dependency_transaction_ids=tuple(transaction.dependency_reference_ids or ()),
        child_sequence_hint=transaction.child_sequence_hint,
        instrument_id=transaction.instrument_id,
        source_instrument_id=transaction.source_instrument_id,
        target_instrument_id=transaction.target_instrument_id,
    )


def _present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
