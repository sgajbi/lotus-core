"""Persist lot-disposal receipts for the exact affected calculation suffix."""

from collections.abc import Sequence, Set

from ...domain.cost_basis import CostBasisTransaction, TransactionLotDisposal
from ...ports import CostBasisLotDisposalPort
from .persistence_scope import affected_transaction_suffix


async def persist_current_lot_disposals(
    *,
    processed: Sequence[CostBasisTransaction],
    incoming_transaction_ids: Set[str],
    disposals: Sequence[TransactionLotDisposal],
    repository: CostBasisLotDisposalPort,
) -> None:
    """Reconcile immutable disposal evidence with the affected transaction suffix."""

    affected = affected_transaction_suffix(
        processed=processed,
        incoming_transaction_ids=incoming_transaction_ids,
    )
    processed_ids = {transaction.transaction_id for transaction in processed}
    disposals_by_transaction: dict[str, TransactionLotDisposal] = {}
    for disposal in disposals:
        transaction_id = disposal.disposal_transaction_id
        if transaction_id not in processed_ids:
            raise ValueError(
                "Lot-disposal evidence references a transaction outside the calculated timeline: "
                f"{transaction_id}"
            )
        if transaction_id in disposals_by_transaction:
            raise ValueError(
                f"Calculated timeline emitted duplicate lot-disposal evidence: {transaction_id}"
            )
        disposals_by_transaction[transaction_id] = disposal

    affected_ids = tuple(transaction.transaction_id for transaction in affected)
    await repository.reconcile_current_disposals(
        affected_transaction_ids=affected_ids,
        disposals=tuple(
            disposals_by_transaction[transaction_id]
            for transaction_id in affected_ids
            if transaction_id in disposals_by_transaction
        ),
    )
