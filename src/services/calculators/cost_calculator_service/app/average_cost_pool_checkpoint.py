from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .cost_engine.processing.cost_objects import OpenLotState

AVERAGE_COST_POOL_STATE_VERSION = "avco-pool-v1"


@dataclass(frozen=True, slots=True)
class AverageCostPoolCheckpoint:
    portfolio_id: str
    instrument_id: str
    security_id: str
    representative_source_transaction_id: str | None
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal
    state_version: str = AVERAGE_COST_POOL_STATE_VERSION

    def __post_init__(self) -> None:
        if self.quantity < Decimal(0):
            raise ValueError("Average cost pool quantity must be nonnegative")
        if self.cost_local < Decimal(0) or self.cost_base < Decimal(0):
            raise ValueError("Average cost pool basis must be nonnegative")
        if self.quantity > Decimal(0) and not self.representative_source_transaction_id:
            raise ValueError("Positive average cost pool requires representative source lineage")
        if self.quantity == Decimal(0) and (
            self.cost_local != Decimal(0) or self.cost_base != Decimal(0)
        ):
            raise ValueError("Closed average cost pool must have zero local and base basis")

    @classmethod
    def from_open_lot_states(
        cls,
        *,
        portfolio_id: str,
        instrument_id: str,
        security_id: str,
        states_by_source_transaction_id: Mapping[str, OpenLotState],
    ) -> AverageCostPoolCheckpoint:
        quantity = sum(
            (state.quantity for state in states_by_source_transaction_id.values()), Decimal(0)
        )
        cost_local = sum(
            (state.cost_local for state in states_by_source_transaction_id.values()), Decimal(0)
        )
        cost_base = sum(
            (state.cost_base for state in states_by_source_transaction_id.values()), Decimal(0)
        )
        representative_source_transaction_id = next(
            (
                source_transaction_id
                for source_transaction_id, state in reversed(
                    tuple(states_by_source_transaction_id.items())
                )
                if state.quantity > Decimal(0)
            ),
            None,
        )
        return cls(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            security_id=security_id,
            representative_source_transaction_id=representative_source_transaction_id,
            quantity=quantity,
            cost_local=cost_local,
            cost_base=cost_base,
        )

    def is_compatible(
        self,
        *,
        portfolio_id: str,
        instrument_id: str,
        security_id: str,
    ) -> bool:
        return (
            self.state_version == AVERAGE_COST_POOL_STATE_VERSION
            and self.portfolio_id == portfolio_id
            and self.instrument_id == instrument_id
            and self.security_id == security_id
        )

    def as_open_lot_state(self) -> OpenLotState:
        return OpenLotState(
            quantity=self.quantity,
            cost_local=self.cost_local,
            cost_base=self.cost_base,
        )
