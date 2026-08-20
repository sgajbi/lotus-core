"""Select the deterministic timeline suffix affected by incoming transactions."""

from collections.abc import Sequence, Set
from dataclasses import dataclass
from enum import StrEnum

from ...domain.cost_basis import CostBasisTransaction


class CostBasisTransactionPersistenceScope(StrEnum):
    """Select which calculated transaction economics require durable refresh."""

    AFFECTED_SUFFIX = "affected_suffix"
    REBUILD_AUTHORITY = "rebuild_authority"


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
    missing_authority_transaction_ids: Set[str] = frozenset(),
) -> CostBasisPersistencePlan:
    """Return calculated rows for canonical economics and child-state persistence.

    A full rebuild must refresh any calculated prefix row that lacks durable cost
    authority because a concurrent command can still be in flight. Already governed
    prefix rows remain untouched so statement count does not grow with history depth.
    """

    affected = affected_transaction_suffix(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
    )
    affected_ids = {transaction.transaction_id for transaction in affected}
    economics = tuple(
        transaction
        for transaction in processed
        if transaction.transaction_id in affected_ids
        or (
            scope is CostBasisTransactionPersistenceScope.REBUILD_AUTHORITY
            and transaction.transaction_id in missing_authority_transaction_ids
        )
    )
    return CostBasisPersistencePlan(
        economics_transactions=economics,
        child_state_transactions=affected,
    )
