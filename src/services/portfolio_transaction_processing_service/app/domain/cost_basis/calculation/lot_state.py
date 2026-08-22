"""Define immutable and mutable state used during lot calculations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import require_sha256_digest
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


def resolve_source_lot_original_quantity(
    *,
    original_quantity: Decimal | None,
    order_quantity: Decimal | None,
    current_quantity: Decimal,
) -> Decimal:
    """Resolve new or restored lot authority without fabricating restored history."""

    if original_quantity is not None:
        return original_quantity
    if order_quantity is not None:
        raise ValueError("Restored source lot is missing original quantity authority")
    return current_quantity


@dataclass(frozen=True, slots=True)
class AmortizedCostCarryState:
    """Independent accounting carrying state for one persisted open lot.

    ``OpenLotState.cost_*`` remains the strategy/tax acquisition basis.  These amounts are the
    residual accounting carrying amount consumed by the fixed-income amortized-cost overlay.
    """

    profile_id: str
    profile_version: int
    profile_content_hash: str
    recognized_through_date: date
    scheduled_cost_local: Decimal
    carrying_amount_local: Decimal
    carrying_amount_base: Decimal
    book_cost_fx_rate_to_base: Decimal

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
        _require_non_negative_decimal(self.carrying_amount_local, "carrying_amount_local")
        _require_non_negative_decimal(self.carrying_amount_base, "carrying_amount_base")
        _require_positive_decimal(
            self.book_cost_fx_rate_to_base,
            "book_cost_fx_rate_to_base",
        )


@dataclass(frozen=True, slots=True)
class OpenLotState:
    original_quantity: Decimal
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    amortized_cost: AmortizedCostCarryState | None = None

    def __post_init__(self) -> None:
        for field_name in ("original_quantity", "quantity", "cost_local", "cost_base"):
            _require_non_negative_decimal(getattr(self, field_name), field_name)
        if self.quantity > self.original_quantity:
            raise ValueError("quantity must not exceed original_quantity")
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
        original_quantity: Decimal | None = None,
    ):
        self.transaction_id = transaction_id
        self.lot_id = lot_id
        self.acquisition_date = acquisition_date
        self.original_quantity = original_quantity if original_quantity is not None else quantity
        if self.original_quantity < quantity:
            raise ValueError("lot original_quantity must not be below open quantity")
        self.remaining_quantity = quantity
        self.cost_per_share_local = cost_per_share_local
        self.cost_per_share_base = cost_per_share_base

    def open_state(self) -> OpenLotState:
        return OpenLotState(
            original_quantity=self.original_quantity,
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
        raise ValueError(f"{field_name} must be a finite Decimal")
    if value < Decimal(0):
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_decimal(value: object, field_name: str) -> None:
    _require_non_negative_decimal(value, field_name)
    if value == Decimal(0):
        raise ValueError(f"{field_name} must be positive")
