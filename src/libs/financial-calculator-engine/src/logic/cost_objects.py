# src/logic/cost_objects.py

from decimal import Decimal


class CostLot:
    """
    Represents a single 'lot' of securities acquired through a BUY transaction,
    tracking cost in both local and base currencies.
    """

    def __init__(
        self,
        transaction_id: str,
        quantity: Decimal,
        cost_per_share_local: Decimal,
        cost_per_share_base: Decimal,
    ):
        self.transaction_id = transaction_id
        self.original_quantity = quantity
        self.remaining_quantity = quantity
        self.cost_per_share_local = cost_per_share_local
        self.cost_per_share_base = cost_per_share_base

    @property
    def total_cost_local(self) -> Decimal:
        """Calculates the total cost of the original lot in the local currency."""
        return self.original_quantity * self.cost_per_share_local

    @property
    def total_cost_base(self) -> Decimal:
        """Calculates the total cost of the original lot in the portfolio's base currency."""
        return self.original_quantity * self.cost_per_share_base

    def __repr__(self) -> str:
        return (
            f"CostLot(txn_id='{self.transaction_id}', "
            f"rem_qty={self.remaining_quantity:.2f}, "
            f"cost_local={self.cost_per_share_local:.4f}, "
            f"cost_base={self.cost_per_share_base:.4f})"
        )
