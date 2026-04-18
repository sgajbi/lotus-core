import logging
from collections import defaultdict, deque
from decimal import Decimal
from typing import Deque, Dict, Optional, Protocol, Tuple

from ..domain.models.transaction import Transaction
from .cost_objects import CostLot

logger = logging.getLogger(__name__)


class CostBasisStrategy(Protocol):
    def add_buy_lot(self, transaction: Transaction): ...
    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal, Optional[str]]: ...
    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal: ...
    def set_initial_lots(self, transactions: list[Transaction]): ...
    def get_open_lot_quantities(self) -> dict[str, Decimal]: ...


class FIFOBasisStrategy:
    """
    Implements the First-In, First-Out (FIFO) cost basis method.
    """

    def __init__(self):
        self._open_lots: Dict[Tuple[str, str], Deque[CostLot]] = defaultdict(deque)
        self._remaining_quantity_by_transaction_id: Dict[str, Decimal] = {}
        logger.debug("FIFOBasisStrategy initialized.")

    def add_buy_lot(self, transaction: Transaction):
        if transaction.net_cost is None or transaction.net_cost_local is None:
            raise ValueError(
                "Buy transaction "
                f"{transaction.transaction_id} must have net_cost and "
                "net_cost_local calculated before adding as a lot."
            )
        if transaction.quantity == Decimal(0):
            return

        cost_per_share_local = transaction.net_cost_local / transaction.quantity
        cost_per_share_base = transaction.net_cost / transaction.quantity

        new_lot = CostLot(
            transaction_id=transaction.transaction_id,
            quantity=transaction.quantity,
            cost_per_share_local=cost_per_share_local,
            cost_per_share_base=cost_per_share_base,
        )
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._open_lots[key].append(new_lot)
        self._remaining_quantity_by_transaction_id[transaction.transaction_id] = (
            transaction.quantity
        )

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal, Optional[str]]:
        key = (portfolio_id, instrument_id)
        required_quantity = sell_quantity
        total_matched_cost_base = Decimal(0)
        total_matched_cost_local = Decimal(0)
        consumed_quantity = Decimal(0)
        available_qty = self.get_available_quantity(portfolio_id=key[0], instrument_id=key[1])

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
            current_lot = lots_for_instrument[0]
            if current_lot.remaining_quantity >= required_quantity:
                total_matched_cost_base += required_quantity * current_lot.cost_per_share_base
                total_matched_cost_local += required_quantity * current_lot.cost_per_share_local
                consumed_quantity += required_quantity
                current_lot.remaining_quantity -= required_quantity
                self._remaining_quantity_by_transaction_id[current_lot.transaction_id] = (
                    current_lot.remaining_quantity
                )
                required_quantity = Decimal(0)

                if current_lot.remaining_quantity == Decimal(0):
                    lots_for_instrument.popleft()
            else:
                total_matched_cost_base += (
                    current_lot.remaining_quantity * current_lot.cost_per_share_base
                )
                total_matched_cost_local += (
                    current_lot.remaining_quantity * current_lot.cost_per_share_local
                )
                consumed_quantity += current_lot.remaining_quantity
                required_quantity -= current_lot.remaining_quantity
                self._remaining_quantity_by_transaction_id[current_lot.transaction_id] = Decimal(0)
                lots_for_instrument.popleft()
        return total_matched_cost_base, total_matched_cost_local, consumed_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return sum(lot.remaining_quantity for lot in self._open_lots[key])

    def set_initial_lots(self, transactions: list[Transaction]):
        for txn in transactions:
            if txn.transaction_type == "BUY":
                self.add_buy_lot(txn)

    def get_open_lot_quantities(self) -> dict[str, Decimal]:
        return dict(self._remaining_quantity_by_transaction_id)


class AverageCostBasisStrategy(CostBasisStrategy):
    """
    Implements the Average Cost (AVCO) method for tracking cost basis,
    with full support for dual-currency calculations.
    """

    def __init__(self):
        self._holdings: Dict[Tuple[str, str], Dict[str, Decimal]] = defaultdict(
            lambda: {
                "total_qty": Decimal(0),
                "total_cost_local": Decimal(0),
                "total_cost_base": Decimal(0),
            }
        )
        logger.debug("AverageCostBasisStrategy initialized.")

    def add_buy_lot(self, transaction: Transaction):
        if transaction.net_cost is None or transaction.net_cost_local is None:
            raise ValueError(
                "Buy transaction "
                f"{transaction.transaction_id} must have net_cost and "
                "net_cost_local calculated."
            )

        key = (transaction.portfolio_id, transaction.instrument_id)
        self._holdings[key]["total_qty"] += transaction.quantity
        self._holdings[key]["total_cost_local"] += transaction.net_cost_local
        self._holdings[key]["total_cost_base"] += transaction.net_cost

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal, Optional[str]]:
        key = (portfolio_id, instrument_id)
        holding = self._holdings[key]
        total_qty = holding["total_qty"]
        required_quantity = sell_quantity

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

        avg_cost_per_share_local = holding["total_cost_local"] / total_qty
        avg_cost_per_share_base = holding["total_cost_base"] / total_qty

        cogs_local = required_quantity * avg_cost_per_share_local
        cogs_base = required_quantity * avg_cost_per_share_base

        holding["total_qty"] -= required_quantity
        holding["total_cost_local"] -= cogs_local
        holding["total_cost_base"] -= cogs_base

        return cogs_base, cogs_local, required_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._holdings[key]["total_qty"]

    def set_initial_lots(self, transactions: list[Transaction]):
        for txn in transactions:
            if txn.transaction_type == "BUY":
                self.add_buy_lot(txn)

    def get_open_lot_quantities(self) -> dict[str, Decimal]:
        return {}
