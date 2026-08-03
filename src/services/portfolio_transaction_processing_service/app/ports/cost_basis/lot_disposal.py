"""Persistence boundary for immutable lot-disposal calculation receipts."""

from typing import Protocol

from ...domain.cost_basis import LotDisposalReceiptState


class CostBasisLotDisposalPort(Protocol):
    """Append disposal receipts and reconcile their current transaction pointers."""

    async def reconcile_disposal_receipts(
        self,
        *,
        receipt_states: tuple[LotDisposalReceiptState, ...],
    ) -> None:
        """Reconcile one immutable state for every affected transaction.

        Implementations must retain all prior versions, classify an exact semantic retry
        as neutral, append changed recalculations contiguously, and represent removal of
        prior disposal evidence with an explicit VOIDED version.
        """

        ...
