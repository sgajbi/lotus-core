"""Define the durable ordering checkpoint for incremental cost-basis processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method

from .calculation.transaction_ordering import TransactionOrderKey, transaction_order_key
from .models.cost_basis_transaction import CostBasisTransaction

COST_BASIS_STATE_VERSION = "open-lot-v1"


@dataclass(frozen=True, slots=True)
class CostBasisProcessingCheckpoint:
    portfolio_id: str
    security_id: str
    cost_basis_method: str
    latest_transaction_date: datetime
    latest_dependency_rank: int
    latest_cash_dependency_rank: int
    latest_child_sequence: int
    latest_target_instrument_id: str
    latest_quantity: Decimal
    latest_transaction_id: str
    calculation_state_version: str = COST_BASIS_STATE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.latest_quantity, Decimal) or not self.latest_quantity.is_finite():
            raise ValueError("Latest cost-basis quantity must be a finite Decimal")
        if self.latest_quantity < Decimal(0):
            raise ValueError("Latest cost-basis quantity must be nonnegative")

    @classmethod
    def from_transaction(
        cls,
        transaction: CostBasisTransaction,
        *,
        cost_basis_method: str | CostBasisMethod,
    ) -> CostBasisProcessingCheckpoint:
        (
            transaction_date,
            dependency_rank,
            cash_dependency_rank,
            child_sequence,
            target_instrument_id,
            _negative_quantity,
            transaction_id,
        ) = transaction_order_key(transaction)
        return cls(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            cost_basis_method=normalize_cost_basis_method(cost_basis_method).value,
            latest_transaction_date=transaction_date,
            latest_dependency_rank=dependency_rank,
            latest_cash_dependency_rank=cash_dependency_rank,
            latest_child_sequence=child_sequence,
            latest_target_instrument_id=target_instrument_id,
            latest_quantity=transaction.quantity,
            latest_transaction_id=transaction_id,
        )

    @property
    def order_key(self) -> TransactionOrderKey:
        return (
            self.latest_transaction_date,
            self.latest_dependency_rank,
            self.latest_cash_dependency_rank,
            self.latest_child_sequence,
            self.latest_target_instrument_id,
            -self.latest_quantity,
            self.latest_transaction_id,
        )

    def permits_append(
        self,
        transaction: CostBasisTransaction,
        *,
        cost_basis_method: str | CostBasisMethod,
    ) -> bool:
        return (
            self.calculation_state_version == COST_BASIS_STATE_VERSION
            and self.cost_basis_method == normalize_cost_basis_method(cost_basis_method).value
            and transaction.portfolio_id == self.portfolio_id
            and transaction.security_id == self.security_id
            and transaction_order_key(transaction) > self.order_key
        )
