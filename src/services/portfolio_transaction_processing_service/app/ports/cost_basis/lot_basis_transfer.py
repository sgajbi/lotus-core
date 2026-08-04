"""Persistence boundary for immutable lot basis-transfer receipts."""

from typing import Protocol

from ...domain.cost_basis import LotBasisTransferReceiptState


class CostBasisLotBasisTransferPort(Protocol):
    """Append current transfer evidence and void removed evidence in an affected suffix."""

    async def reconcile_basis_transfer_receipts(
        self,
        *,
        affected_source_transaction_ids: tuple[str, ...],
        receipt_states: tuple[LotBasisTransferReceiptState, ...],
    ) -> None:
        """Reconcile versioned evidence without rewriting prior receipt versions."""

        ...
