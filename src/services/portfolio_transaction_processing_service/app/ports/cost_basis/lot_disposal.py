"""Persistence boundary for immutable lot-disposal calculation receipts."""

from typing import Protocol

from ...domain.cost_basis import TransactionLotDisposal


class CostBasisLotDisposalPort(Protocol):
    """Append disposal receipts and reconcile their current transaction pointers."""

    async def reconcile_current_disposals(
        self,
        *,
        affected_transaction_ids: tuple[str, ...],
        disposals: tuple[TransactionLotDisposal, ...],
    ) -> None:
        """Persist current receipts for one deterministic recalculation suffix.

        Implementations must retain previously recorded receipt versions, classify an
        exact retry as neutral, reject conflicting receipt content, and atomically move
        or clear the current pointer for every affected transaction.
        """

        ...
