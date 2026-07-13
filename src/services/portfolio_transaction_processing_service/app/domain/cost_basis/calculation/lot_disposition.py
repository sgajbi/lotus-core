"""Coordinate opening-lot restoration, acquisition, and disposition."""

import logging
from decimal import Decimal

from portfolio_common.domain.decimal_amount import required_decimal

from ..models.cost_basis_transaction import CostBasisTransaction
from .cost_basis_strategies import CostBasisStrategy
from .lot_state import OpenLotState

logger = logging.getLogger(__name__)


def _is_buy_transaction(transaction: CostBasisTransaction) -> bool:
    return str(transaction.transaction_type or "").strip().upper() == "BUY"


class LotDispositionEngine:
    """
    Manages 'cost lots', delegating calculation logic to a specific strategy.
    """

    def __init__(self, cost_basis_strategy: CostBasisStrategy):
        self._cost_basis_strategy = cost_basis_strategy

    def add_buy_lot(self, transaction: CostBasisTransaction):
        if transaction.quantity > Decimal(0):
            self._cost_basis_strategy.add_buy_lot(transaction)

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        return self._cost_basis_strategy.get_available_quantity(portfolio_id, instrument_id)

    def consume_sell_quantity(
        self, transaction: CostBasisTransaction
    ) -> tuple[Decimal, Decimal, Decimal, str | None]:
        sell_quantity = required_decimal(transaction.quantity, field_name="quantity")
        return self._cost_basis_strategy.consume_sell_quantity(
            transaction.portfolio_id, transaction.instrument_id, sell_quantity
        )

    def transfer_basis_out(
        self,
        transaction: CostBasisTransaction,
        *,
        cost_base: Decimal,
        cost_local: Decimal,
    ) -> str | None:
        return self._cost_basis_strategy.transfer_basis_out(
            transaction.portfolio_id,
            transaction.instrument_id,
            cost_base,
            cost_local,
        )

    def set_initial_lots(self, transactions: list[CostBasisTransaction]):
        filtered_buys = [
            txn for txn in transactions if _is_buy_transaction(txn) and txn.quantity > Decimal(0)
        ]
        self._cost_basis_strategy.set_initial_lots(filtered_buys)

    def restore_open_lots(self, transactions: list[CostBasisTransaction]) -> None:
        self._cost_basis_strategy.restore_open_lots(transactions)

    def get_open_lot_states(self) -> dict[str, OpenLotState]:
        return self._cost_basis_strategy.get_open_lot_states()
