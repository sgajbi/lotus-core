import logging
from decimal import Decimal
from typing import Optional, Tuple

from portfolio_common.decimal_amounts import required_decimal

from ..domain.models.transaction import Transaction
from .cost_basis_strategies import CostBasisStrategy

logger = logging.getLogger(__name__)


def _is_buy_transaction(transaction: Transaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


class DispositionEngine:
    """
    Manages 'cost lots', delegating calculation logic to a specific strategy.
    """

    def __init__(self, cost_basis_strategy: CostBasisStrategy):
        self._cost_basis_strategy = cost_basis_strategy

    def add_buy_lot(self, transaction: Transaction):
        if transaction.quantity > Decimal(0):
            self._cost_basis_strategy.add_buy_lot(transaction)

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        return self._cost_basis_strategy.get_available_quantity(portfolio_id, instrument_id)

    def consume_sell_quantity(
        self, transaction: Transaction
    ) -> Tuple[Decimal, Decimal, Optional[str]]:
        sell_quantity = required_decimal(transaction.quantity, field_name="quantity")
        return self._cost_basis_strategy.consume_sell_quantity(
            transaction.portfolio_id, transaction.instrument_id, sell_quantity
        )

    def set_initial_lots(self, transactions: list[Transaction]):
        filtered_buys = [
            txn for txn in transactions if _is_buy_transaction(txn) and txn.quantity > Decimal(0)
        ]
        self._cost_basis_strategy.set_initial_lots(filtered_buys)

    def get_open_lot_quantities(self) -> dict[str, Decimal]:
        return self._cost_basis_strategy.get_open_lot_quantities()
