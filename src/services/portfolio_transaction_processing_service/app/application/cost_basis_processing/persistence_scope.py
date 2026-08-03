"""Select the deterministic timeline suffix affected by incoming transactions."""

from collections.abc import Sequence, Set

from ...domain.cost_basis import CostBasisTransaction


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
