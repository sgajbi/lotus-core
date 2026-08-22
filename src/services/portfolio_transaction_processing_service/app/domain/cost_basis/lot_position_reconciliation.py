"""Domain records for bounded lot-to-position quantity reconciliation."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

LOT_QUANTITY_VS_POSITION_MISMATCH = "lot_quantity_vs_position_mismatch"


@dataclass(frozen=True, order=True, slots=True)
class LotPositionParityKey:
    portfolio_id: str
    security_id: str

    def __post_init__(self) -> None:
        if not self.portfolio_id.strip() or not self.security_id.strip():
            raise ValueError("Lot-position parity identifiers must not be blank")


class LotPositionParityStatus(StrEnum):
    CURRENT = "current"
    DRIFTED = "drifted"


@dataclass(frozen=True, slots=True)
class LotPositionParityAssessment:
    key: LotPositionParityKey
    epoch: int
    lot_quantity: Decimal
    position_quantity: Decimal | None
    status: LotPositionParityStatus
    finding_type: str | None = None

    def __post_init__(self) -> None:
        if self.epoch < 0:
            raise ValueError("Lot-position parity epoch must be nonnegative")
        if self.lot_quantity < Decimal(0):
            raise ValueError("Lot quantity must be nonnegative")
        matches = self.position_quantity is not None and (
            self.lot_quantity == self.position_quantity
        )
        if self.status is LotPositionParityStatus.CURRENT:
            if not matches or self.finding_type is not None:
                raise ValueError("Current lot-position state must reconcile exactly")
        elif matches or self.finding_type != LOT_QUANTITY_VS_POSITION_MISMATCH:
            raise ValueError("Drifted lot-position state requires the governed finding type")
