import logging
from collections import defaultdict, deque
from decimal import Decimal
from typing import Protocol

from portfolio_common.decimal_amounts import required_decimal

from ..domain.models.transaction import Transaction
from .average_cost_source_allocation import (
    AverageCostPool,
    AverageCostSourceAllocation,
)
from .cost_objects import CostLot, OpenLotState

logger = logging.getLogger(__name__)


def _is_buy_transaction(transaction: Transaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


def _require_buy_lot_cost_basis(transaction: Transaction) -> None:
    if transaction.net_cost is not None and transaction.net_cost_local is not None:
        return
    raise ValueError(
        "Buy transaction "
        f"{transaction.transaction_id} must have net_cost and "
        "net_cost_local calculated before adding as a lot."
    )


def _normalized_buy_lot_amounts(transaction: Transaction) -> tuple[Decimal, Decimal, Decimal]:
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
    transaction: Transaction, quantity: Decimal, net_cost: Decimal, net_cost_local: Decimal
) -> bool:
    if quantity > Decimal(0):
        return False
    if _is_zero_quantity_zero_cost_lot(quantity, net_cost, net_cost_local):
        return True
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have positive lot quantity."
    )


def _validate_non_negative_buy_lot_cost_basis(
    transaction: Transaction, net_cost: Decimal, net_cost_local: Decimal
) -> None:
    if net_cost >= Decimal(0) and net_cost_local >= Decimal(0):
        return
    raise ValueError(
        f"Buy transaction {transaction.transaction_id} must have non-negative lot cost basis."
    )


def _validated_buy_lot_inputs(transaction: Transaction) -> tuple[Decimal, Decimal, Decimal] | None:
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
    def add_buy_lot(self, transaction: Transaction) -> None: ...
    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, str | None]: ...
    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal: ...
    def set_initial_lots(self, transactions: list[Transaction]) -> None: ...
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

    def add_buy_lot(self, transaction: Transaction) -> None:
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

    def set_initial_lots(self, transactions: list[Transaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

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

    def add_buy_lot(self, transaction: Transaction) -> None:
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

    def set_initial_lots(self, transactions: list[Transaction]) -> None:
        for txn in transactions:
            if _is_buy_transaction(txn):
                self.add_buy_lot(txn)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return self._source_allocation.materialize(self._pools)
