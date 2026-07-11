"""Implement FIFO and average-cost lot allocation strategies."""

import logging
from collections import defaultdict, deque
from decimal import Decimal
from typing import Protocol

from portfolio_common.decimal_amounts import required_decimal

from ..models.cost_basis_transaction import CostBasisTransaction
from .average_cost_source_allocation import (
    AverageCostPool,
    AverageCostSourceAllocation,
)
from .lot_state import CostLot, OpenLotState

logger = logging.getLogger(__name__)


def _is_buy_transaction(transaction: CostBasisTransaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


def _require_buy_lot_cost_basis(transaction: CostBasisTransaction) -> None:
    if transaction.net_cost is not None and transaction.net_cost_local is not None:
        return
    raise ValueError(
        "Buy transaction "
        f"{transaction.transaction_id} must have net_cost and "
        "net_cost_local calculated before adding as a lot."
    )


def _normalized_buy_lot_amounts(
    transaction: CostBasisTransaction,
) -> tuple[Decimal, Decimal, Decimal]:
    return (
        required_decimal(transaction.quantity, field_name="quantity"),
        required_decimal(transaction.net_cost, field_name="net_cost"),
        required_decimal(transaction.net_cost_local, field_name="net_cost_local"),
    )


def _is_zero_quantity_zero_cost_lot(
    quantity: Decimal, net_cost: Decimal, net_cost_local: Decimal
) -> bool:
    return quantity == Decimal(0) and net_cost == Decimal(0) and net_cost_local == Decimal(0)


def _should_skip_empty_buy_lot(
    transaction: CostBasisTransaction, quantity: Decimal, net_cost: Decimal, net_cost_local: Decimal
) -> bool:
    if quantity > Decimal(0):
        return False
    if _is_zero_quantity_zero_cost_lot(quantity, net_cost, net_cost_local):
        return True
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have positive lot quantity."
    )


def _validate_non_negative_buy_lot_cost_basis(
    transaction: CostBasisTransaction, net_cost: Decimal, net_cost_local: Decimal
) -> None:
    if net_cost >= Decimal(0) and net_cost_local >= Decimal(0):
        return
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have non-negative lot cost basis."
    )


def _validated_buy_lot_inputs(
    transaction: CostBasisTransaction,
) -> tuple[Decimal, Decimal, Decimal] | None:
    _require_buy_lot_cost_basis(transaction)
    quantity, net_cost, net_cost_local = _normalized_buy_lot_amounts(transaction)
    if _should_skip_empty_buy_lot(transaction, quantity, net_cost, net_cost_local):
        return None
    _validate_non_negative_buy_lot_cost_basis(transaction, net_cost, net_cost_local)
    return quantity, net_cost, net_cost_local


def _non_positive_sell_quantity_error(sell_quantity: Decimal) -> str | None:
    if sell_quantity >= Decimal(0):
        return None
    return f"Sell quantity ({sell_quantity}) must not be negative."


def _consume_next_fifo_lot(
    lots_for_instrument: deque[CostLot],
    required_quantity: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    current_lot = lots_for_instrument[0]
    matched_quantity = min(required_quantity, current_lot.remaining_quantity)
    matched_cost_base = matched_quantity * current_lot.cost_per_share_base
    matched_cost_local = matched_quantity * current_lot.cost_per_share_local

    current_lot.remaining_quantity -= matched_quantity
    if current_lot.remaining_quantity == Decimal(0):
        lots_for_instrument.popleft()

    return (
        matched_cost_base,
        matched_cost_local,
        matched_quantity,
        required_quantity - matched_quantity,
    )


class CostBasisStrategy(Protocol):
    def add_buy_lot(self, transaction: CostBasisTransaction) -> None: ...
    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]: ...
    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal: ...
    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None: ...
    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None: ...
    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None: ...
    def get_open_lot_states(self) -> dict[str, OpenLotState]: ...


class FIFOBasisStrategy:
    """
    Implements the First-In, First-Out (FIFO) cost basis method.
    """

    def __init__(self) -> None:
        self._open_lots: dict[tuple[str, str], deque[CostLot]] = defaultdict(deque)
        self._lots_by_transaction_id: dict[str, CostLot] = {}
        self._available_quantities: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
        logger.debug("FIFOBasisStrategy initialized.")

    def add_buy_lot(self, transaction: CostBasisTransaction) -> None:
        validated_inputs = _validated_buy_lot_inputs(transaction)
        if validated_inputs is None:
            return
        quantity, net_cost, net_cost_local = validated_inputs

        cost_per_share_local = net_cost_local / quantity
        cost_per_share_base = net_cost / quantity

        new_lot = CostLot(
            transaction_id=transaction.transaction_id,
            quantity=quantity,
            cost_per_share_local=cost_per_share_local,
            cost_per_share_base=cost_per_share_base,
        )
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._open_lots[key].append(new_lot)
        self._lots_by_transaction_id[transaction.transaction_id] = new_lot
        self._available_quantities[key] += quantity

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        key = (portfolio_id, instrument_id)
        required_quantity = sell_quantity
        total_matched_cost_base = Decimal(0)
        total_matched_cost_local = Decimal(0)
        consumed_quantity = Decimal(0)
        available_qty = self.get_available_quantity(portfolio_id=key[0], instrument_id=key[1])
        invalid_quantity_error = _non_positive_sell_quantity_error(required_quantity)
        if invalid_quantity_error is not None:
            return Decimal(0), Decimal(0), Decimal(0), invalid_quantity_error

        if required_quantity > available_qty:
            return (
                Decimal(0),
                Decimal(0),
                Decimal(0),
                "Sell quantity "
                f"({required_quantity}) exceeds available holdings "
                f"({available_qty}).",
            )

        lots_for_instrument = self._open_lots[key]
        while required_quantity > 0 and lots_for_instrument:
            matched_cost_base, matched_cost_local, matched_quantity, required_quantity = (
                _consume_next_fifo_lot(
                    lots_for_instrument,
                    required_quantity,
                )
            )
            total_matched_cost_base += matched_cost_base
            total_matched_cost_local += matched_cost_local
            consumed_quantity += matched_quantity
        self._available_quantities[key] = available_qty - consumed_quantity
        return total_matched_cost_base, total_matched_cost_local, consumed_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._available_quantities[key]

    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None:
        lots = self._open_lots[(portfolio_id, instrument_id)]
        error = _basis_transfer_error(lots, cost_base=cost_base, cost_local=cost_local)
        if error is not None:
            return error
        _allocate_fifo_basis_transfer(lots, cost_base=cost_base, cost_local=cost_local)
        return None

    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for transaction in transactions:
            self.add_buy_lot(transaction)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return {
            transaction_id: lot.open_state()
            for transaction_id, lot in self._lots_by_transaction_id.items()
        }


class AverageCostBasisStrategy(CostBasisStrategy):
    """
    Implements the Average Cost (AVCO) method for tracking cost basis,
    with full support for dual-currency calculations.
    """

    def __init__(self) -> None:
        self._pools: dict[tuple[str, str], AverageCostPool] = defaultdict(AverageCostPool)
        self._source_allocation = AverageCostSourceAllocation()
        logger.debug("AverageCostBasisStrategy initialized.")

    def add_buy_lot(self, transaction: CostBasisTransaction) -> None:
        validated_inputs = _validated_buy_lot_inputs(transaction)
        if validated_inputs is None:
            return
        quantity, net_cost, net_cost_local = validated_inputs

        key = (transaction.portfolio_id, transaction.instrument_id)
        self._pools[key].add(
            quantity=quantity,
            cost_local=net_cost_local,
            cost_base=net_cost,
        )
        self._source_allocation.add_source(
            book_key=key,
            source_transaction_id=transaction.transaction_id,
            quantity=quantity,
            cost_local=net_cost_local,
            cost_base=net_cost,
            pool_quantity_after=self._pools[key].quantity,
        )

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        key = (portfolio_id, instrument_id)
        pool = self._pools[key]
        total_qty = pool.quantity
        required_quantity = sell_quantity
        invalid_quantity_error = _non_positive_sell_quantity_error(required_quantity)
        if invalid_quantity_error is not None:
            return Decimal(0), Decimal(0), Decimal(0), invalid_quantity_error

        if required_quantity > total_qty:
            return (
                Decimal(0),
                Decimal(0),
                Decimal(0),
                "Sell quantity "
                f"({required_quantity}) exceeds available average cost "
                f"holdings ({total_qty}).",
            )
        if total_qty.is_zero():
            return (
                Decimal(0),
                Decimal(0),
                Decimal(0),
                "No holdings to sell against (Average Cost method).",
            )

        cogs_base, cogs_local = pool.dispose(required_quantity)
        self._source_allocation.apply_disposal(
            book_key=key,
            quantity_before=total_qty,
            quantity_after=pool.quantity,
        )

        return cogs_base, cogs_local, required_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._pools[key].quantity

    def transfer_basis_out(
        self,
        portfolio_id: str,
        instrument_id: str,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None:
        key = (portfolio_id, instrument_id)
        pool = self._pools[key]
        error = _pool_basis_transfer_error(
            pool,
            cost_base=cost_base,
            cost_local=cost_local,
        )
        if error is not None:
            return error
        cost_local_before = pool.cost_local
        cost_base_before = pool.cost_base
        pool.transfer_basis_out(cost_local=cost_local, cost_base=cost_base)
        self._source_allocation.apply_basis_transfer(
            book_key=key,
            cost_local_before=cost_local_before,
            cost_local_after=pool.cost_local,
            cost_base_before=cost_base_before,
            cost_base_after=pool.cost_base,
        )
        return None

    def set_initial_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        for transaction in transactions:
            self.add_buy_lot(transaction)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return self._source_allocation.materialize(self._pools)


def _basis_transfer_error(
    lots: deque[CostLot],
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> str | None:
    total_base = sum((lot.open_state().cost_base for lot in lots), Decimal(0))
    total_local = sum((lot.open_state().cost_local for lot in lots), Decimal(0))
    return _basis_transfer_amount_error(
        cost_base=cost_base,
        cost_local=cost_local,
        available_base=total_base,
        available_local=total_local,
    )


def _pool_basis_transfer_error(
    pool: AverageCostPool,
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> str | None:
    return _basis_transfer_amount_error(
        cost_base=cost_base,
        cost_local=cost_local,
        available_base=pool.cost_base,
        available_local=pool.cost_local,
    )


def _basis_transfer_amount_error(
    *,
    cost_base: Decimal,
    cost_local: Decimal,
    available_base: Decimal,
    available_local: Decimal,
) -> str | None:
    if cost_base < Decimal(0) or cost_local < Decimal(0):
        return "Basis transfer amounts must not be negative."
    if cost_base > available_base or cost_local > available_local:
        return (
            "Basis transfer exceeds available cost basis "
            f"(requested_base={cost_base}, available_base={available_base}, "
            f"requested_local={cost_local}, available_local={available_local})."
        )
    if available_base <= Decimal(0) or available_local <= Decimal(0):
        return "No positive cost basis is available to transfer."
    return None


def _allocate_fifo_basis_transfer(
    lots: deque[CostLot],
    *,
    cost_base: Decimal,
    cost_local: Decimal,
) -> None:
    open_lots = [lot for lot in lots if lot.remaining_quantity > Decimal(0)]
    total_base = sum((lot.open_state().cost_base for lot in open_lots), Decimal(0))
    total_local = sum((lot.open_state().cost_local for lot in open_lots), Decimal(0))
    remaining_base = total_base - cost_base
    remaining_local = total_local - cost_local
    allocated_base = Decimal(0)
    allocated_local = Decimal(0)
    for lot in open_lots[:-1]:
        state = lot.open_state()
        next_base = state.cost_base * remaining_base / total_base
        next_local = state.cost_local * remaining_local / total_local
        lot.cost_per_share_base = next_base / lot.remaining_quantity
        lot.cost_per_share_local = next_local / lot.remaining_quantity
        allocated_base += next_base
        allocated_local += next_local
    final_lot = open_lots[-1]
    final_lot.cost_per_share_base = (remaining_base - allocated_base) / final_lot.remaining_quantity
    final_lot.cost_per_share_local = (
        remaining_local - allocated_local
    ) / final_lot.remaining_quantity
