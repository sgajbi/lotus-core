"""Coordinate opening-lot restoration, acquisition, and disposition."""

from decimal import Decimal
from typing import cast

from portfolio_common.domain.decimal_amount import required_decimal

from ..models.cost_basis_transaction import CostBasisTransaction
from .basis_transfer_allocation import LotBasisTransferResult, TransactionLotBasisTransfer
from .cost_basis_strategies import CostBasisStrategy
from .disposal_allocation import LotDisposalResult, TransactionLotDisposal
from .lot_restatement import LotRestatement
from .lot_state import OpenLotState


def _is_buy_transaction(transaction: CostBasisTransaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


def _normalized_transaction_id(transaction_id: str) -> str:
    if not isinstance(transaction_id, str):
        raise TypeError("transaction_id must be a string")
    normalized = transaction_id.strip()
    if not normalized:
        raise ValueError("transaction_id must be nonblank")
    return normalized


class LotDispositionEngine:
    """
    Manages 'cost lots', delegating calculation logic to a specific strategy.
    """

    def __init__(self, cost_basis_strategy: CostBasisStrategy) -> None:
        self._cost_basis_strategy = cost_basis_strategy
        self._pending_disposals_by_transaction_id: dict[str, TransactionLotDisposal] = {}
        self._disposals_by_transaction_id: dict[str, TransactionLotDisposal] = {}
        self._pending_basis_transfers_by_transaction_id: dict[str, TransactionLotBasisTransfer] = {}
        self._basis_transfers_by_transaction_id: dict[str, TransactionLotBasisTransfer] = {}

    def add_buy_lot(self, transaction: CostBasisTransaction) -> None:
        if transaction.quantity > Decimal(0):
            self._cost_basis_strategy.add_buy_lot(transaction)

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        return cast(
            Decimal,
            self._cost_basis_strategy.get_available_quantity(portfolio_id, instrument_id),
        )

    def restate_lot_quantities(
        self,
        transaction: CostBasisTransaction,
        *,
        signed_quantity_delta: Decimal,
    ) -> LotRestatement:
        """Apply one same-instrument quantity change to the complete open lot book."""

        return self._cost_basis_strategy.restate_lot_quantities(
            transaction.portfolio_id,
            transaction.instrument_id,
            signed_quantity_delta,
        )

    def consume_sell_quantity(
        self, transaction: CostBasisTransaction
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        return self.consume_sell_quantity_with_allocations(transaction).legacy_tuple()

    def consume_sell_quantity_with_allocations(
        self,
        transaction: CostBasisTransaction,
    ) -> LotDisposalResult:
        """Consume quantity and return exact source-lot evidence."""

        sell_quantity = required_decimal(transaction.quantity, field_name="quantity")
        result = cast(
            LotDisposalResult,
            self._cost_basis_strategy.consume_sell_quantity_with_allocations(
                transaction.portfolio_id,
                transaction.instrument_id,
                sell_quantity,
            ),
        )
        if result.error_reason is None and result.consumed_quantity > Decimal(0):
            self._stage_disposal(
                TransactionLotDisposal(
                    disposal_transaction_id=transaction.transaction_id,
                    result=result,
                )
            )
        return result

    def commit_disposal_record(self, transaction_id: str) -> None:
        """Publish staged evidence only after the complete transaction calculation succeeds."""

        pending = self._pending_disposals_by_transaction_id.pop(
            _normalized_transaction_id(transaction_id),
            None,
        )
        if pending is not None:
            self._record_disposal(pending)
        pending_basis_transfer = self._pending_basis_transfers_by_transaction_id.pop(
            _normalized_transaction_id(transaction_id),
            None,
        )
        if pending_basis_transfer is not None:
            self._record_basis_transfer(pending_basis_transfer)

    def discard_pending_disposal(self, transaction_id: str) -> None:
        """Discard evidence for a rejected or interrupted transaction calculation."""

        self._pending_disposals_by_transaction_id.pop(
            _normalized_transaction_id(transaction_id),
            None,
        )
        self._pending_basis_transfers_by_transaction_id.pop(
            _normalized_transaction_id(transaction_id),
            None,
        )

    def disposal_records(
        self,
        *,
        transaction_ids: set[str] | None = None,
    ) -> tuple[TransactionLotDisposal, ...]:
        """Return recorded successful disposals in calculation order."""

        normalized_transaction_ids = (
            None
            if transaction_ids is None
            else {_normalized_transaction_id(transaction_id) for transaction_id in transaction_ids}
        )
        return tuple(
            disposal
            for transaction_id, disposal in self._disposals_by_transaction_id.items()
            if normalized_transaction_ids is None or transaction_id in normalized_transaction_ids
        )

    def clear_disposal_records(self) -> None:
        """Clear staged disposal evidence before a new timeline execution."""

        self._pending_disposals_by_transaction_id.clear()
        self._disposals_by_transaction_id.clear()
        self._pending_basis_transfers_by_transaction_id.clear()
        self._basis_transfers_by_transaction_id.clear()

    def basis_transfer_records(
        self,
        *,
        transaction_ids: set[str] | None = None,
    ) -> tuple[TransactionLotBasisTransfer, ...]:
        """Return accepted basis-only source-to-target evidence in calculation order."""

        normalized_transaction_ids = (
            None
            if transaction_ids is None
            else {_normalized_transaction_id(transaction_id) for transaction_id in transaction_ids}
        )
        return tuple(
            transfer
            for transaction_id, transfer in self._basis_transfers_by_transaction_id.items()
            if normalized_transaction_ids is None or transaction_id in normalized_transaction_ids
        )

    def _stage_disposal(self, disposal: TransactionLotDisposal) -> None:
        transaction_id = disposal.disposal_transaction_id
        existing = self._pending_disposals_by_transaction_id.get(
            transaction_id
        ) or self._disposals_by_transaction_id.get(transaction_id)
        if existing is not None and existing != disposal:
            raise ValueError("one disposal transaction produced conflicting source-lot evidence")
        self._pending_disposals_by_transaction_id[transaction_id] = disposal

    def _record_disposal(self, disposal: TransactionLotDisposal) -> None:
        existing = self._disposals_by_transaction_id.get(disposal.disposal_transaction_id)
        if existing is not None and existing != disposal:
            raise ValueError("one disposal transaction produced conflicting source-lot evidence")
        self._disposals_by_transaction_id[disposal.disposal_transaction_id] = disposal

    def _stage_basis_transfer(self, transfer: TransactionLotBasisTransfer) -> None:
        transaction_id = transfer.source_transaction_id
        existing = self._pending_basis_transfers_by_transaction_id.get(
            transaction_id
        ) or self._basis_transfers_by_transaction_id.get(transaction_id)
        if existing is not None and existing != transfer:
            raise ValueError("one source transaction produced conflicting basis-transfer evidence")
        self._pending_basis_transfers_by_transaction_id[transaction_id] = transfer

    def _record_basis_transfer(self, transfer: TransactionLotBasisTransfer) -> None:
        existing = self._basis_transfers_by_transaction_id.get(transfer.source_transaction_id)
        if existing is not None and existing != transfer:
            raise ValueError("one source transaction produced conflicting basis-transfer evidence")
        self._basis_transfers_by_transaction_id[transfer.source_transaction_id] = transfer

    def transfer_basis_out(
        self,
        transaction: CostBasisTransaction,
        *,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> LotBasisTransferResult:
        target_transaction_id = getattr(transaction, "target_transaction_reference", None)
        if not isinstance(target_transaction_id, str) or not target_transaction_id.strip():
            return LotBasisTransferResult.failed(
                "Basis-only transfer requires target_transaction_reference."
            )
        result = cast(
            LotBasisTransferResult,
            self._cost_basis_strategy.transfer_basis_out_with_allocations(
                transaction.portfolio_id,
                transaction.instrument_id,
                cost_base,
                cost_local,
            ),
        )
        if result.error_reason is None:
            self._stage_basis_transfer(
                TransactionLotBasisTransfer(
                    source_transaction_id=transaction.transaction_id,
                    target_transaction_id=target_transaction_id,
                    target_lot_id=f"LOT-{target_transaction_id.strip()}",
                    result=result,
                )
            )
        return result

    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None:
        filtered_buys = [
            txn for txn in transactions if _is_buy_transaction(txn) and txn.quantity > Decimal(0)
        ]
        self._cost_basis_strategy.set_initial_lots(filtered_buys)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        self._cost_basis_strategy.restore_open_lots(transactions)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return cast(dict[str, OpenLotState], self._cost_basis_strategy.get_open_lot_states())
