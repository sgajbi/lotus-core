"""Select the deterministic timeline suffix affected by incoming transactions."""

from collections.abc import Sequence, Set
from dataclasses import dataclass
from enum import StrEnum

from ...domain.cost_basis import CostBasisTransaction


class CostBasisTransactionPersistenceScope(StrEnum):
    """Select which calculated transaction economics require durable refresh."""

    AFFECTED_SUFFIX = "affected_suffix"
    COMPLETE_TIMELINE = "complete_timeline"


@dataclass(frozen=True, slots=True)
class CostBasisPersistencePlan:
    """Separate canonical economics refresh from affected child-state writes."""

    economics_transactions: tuple[CostBasisTransaction, ...]
    child_state_transactions: tuple[CostBasisTransaction, ...]


def affected_transaction_suffix(
    *,
    processed: Sequence[CostBasisTransaction],
    incoming_transaction_ids: Set[str],
) -> tuple[CostBasisTransaction, ...]:
    """Return every calculated transaction at or after the first incoming transaction.

    A backdated transaction can change the economics and source-lot allocation of every
    later transaction. Persistence callers must therefore use this same suffix for all
    calculated state rather than independently selecting rows by transaction identity.
    """

    first_affected_index = next(
        (
            index
            for index, transaction in enumerate(processed)
            if transaction.transaction_id in incoming_transaction_ids
        ),
        None,
    )
    if first_affected_index is None:
        raise ValueError("Processed transaction timeline omitted the incoming transaction")
    return tuple(processed[first_affected_index:])


def build_cost_basis_persistence_plan(
    *,
    processed: Sequence[CostBasisTransaction],
    incoming_transaction_ids: Set[str],
    scope: CostBasisTransactionPersistenceScope,
) -> CostBasisPersistencePlan:
    """Return calculated rows for canonical economics and child-state persistence.

    A full rebuild must persist the complete calculated timeline because another
    transaction can exist durably without its derived cost authority while a
    concurrent command is still in flight. Position history consumes those canonical
    rows later in the same unit of work.
    """

    affected = affected_transaction_suffix(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
    )
    economics = (
        tuple(processed)
        if scope is CostBasisTransactionPersistenceScope.COMPLETE_TIMELINE
        else affected
    )
    return CostBasisPersistencePlan(
        economics_transactions=economics,
        child_state_transactions=affected,
    )
