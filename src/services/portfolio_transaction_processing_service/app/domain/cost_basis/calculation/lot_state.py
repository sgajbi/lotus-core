"""Define immutable and mutable state used during lot calculations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import require_sha256_digest
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


@dataclass(frozen=True, slots=True)
class AmortizedCostCarryState:
    """Recognition baseline required to advance a persisted amortized open lot."""

    profile_id: str
    profile_version: int
    profile_content_hash: str
    recognized_through_date: date
    scheduled_cost_local: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str):
            raise TypeError("profile_id must be a string")
        normalized_profile_id = self.profile_id.strip()
        if not normalized_profile_id:
            raise ValueError("profile_id must be nonblank")
        object.__setattr__(self, "profile_id", normalized_profile_id)
        if not isinstance(self.profile_version, int) or isinstance(self.profile_version, bool):
            raise TypeError("profile_version must be an integer")
        if self.profile_version < 1:
            raise ValueError("profile_version must be positive")
        require_sha256_digest(self.profile_content_hash, "profile_content_hash")
        if type(self.recognized_through_date) is not date:
            raise TypeError("recognized_through_date must be a date")
        _require_non_negative_decimal(self.scheduled_cost_local, "scheduled_cost_local")


@dataclass(frozen=True, slots=True)
class OpenLotState:
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    amortized_cost: AmortizedCostCarryState | None = None

    def __post_init__(self) -> None:
        for field_name in ("quantity", "cost_local", "cost_base"):
            _require_non_negative_decimal(getattr(self, field_name), field_name)
        if self.quantity == Decimal(0) and self.amortized_cost is not None:
            raise ValueError("closed lot state must not retain amortized-cost carry state")
        if self.amortized_cost is not None and not isinstance(
            self.amortized_cost, AmortizedCostCarryState
        ):
            raise TypeError("amortized_cost must be an AmortizedCostCarryState or None")


class CostLot:
    """
    Represents a single 'lot' of securities acquired through a BUY transaction,
    tracking cost in both local and base currencies.
    """

    def __init__(
        self,
        transaction_id: str,
        lot_id: str,
        acquisition_date: date,
        quantity: Decimal,
        cost_per_share_local: Decimal,
        cost_per_share_base: Decimal,
    ):
        self.transaction_id = transaction_id
        self.lot_id = lot_id
        self.acquisition_date = acquisition_date
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


def _require_non_negative_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < Decimal(0):
        raise ValueError(f"{field_name} must be non-negative")
