# libs/financial-calculator-engine/src/logic/disposition_engine.py
import logging
from decimal import Decimal
from typing import Optional, Tuple

from core.models.transaction import Transaction
from logic.cost_basis_strategies import CostBasisStrategy

logger = logging.getLogger(__name__)

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

    def consume_sell_quantity(self, transaction: Transaction) -> Tuple[Decimal, Decimal, Optional[str]]:
        sell_quantity = Decimal(str(transaction.quantity))
        return self._cost_basis_strategy.consume_sell_quantity(
            transaction.portfolio_id, transaction.instrument_id, sell_quantity
        )

    def set_initial_lots(self, transactions: list[Transaction]):
        from core.enums.transaction_type import TransactionType
        filtered_buys = [
            txn for txn in transactions if txn.transaction_type == TransactionType.BUY and txn.quantity > Decimal(0)
        ]
        self._cost_basis_strategy.set_initial_lots(filtered_buys)