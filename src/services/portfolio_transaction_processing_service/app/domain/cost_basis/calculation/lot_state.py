"""Define immutable and mutable state used during lot calculations."""

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


@dataclass(frozen=True, slots=True)
class OpenLotState:
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal


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

    def open_state(self) -> OpenLotState:
        return OpenLotState(
            quantity=self.remaining_quantity,
            cost_local=COST_BASIS_STATE_LEDGER_OUTPUT_V1.multiply(
                self.remaining_quantity,
                self.cost_per_share_local,
                field_name="lot_cost_local",
            ),
            cost_base=COST_BASIS_STATE_LEDGER_OUTPUT_V1.multiply(
                self.remaining_quantity,
                self.cost_per_share_base,
                field_name="lot_cost_base",
            ),
        )

    def __repr__(self) -> str:
        return (
            f"CostLot(txn_id='{self.transaction_id}', "
            f"rem_qty={self.remaining_quantity:.2f}, "
            f"cost_local={self.cost_per_share_local:.4f}, "
            f"cost_base={self.cost_per_share_base:.4f})"
        )
