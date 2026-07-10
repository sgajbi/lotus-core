from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
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


@dataclass(frozen=True, slots=True)
class AverageCostPoolTransition:
    before: AverageCostPoolCheckpoint
    existing_sources_after: OpenLotState
    explicit_sources_after: Mapping[str, OpenLotState]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "explicit_sources_after",
            MappingProxyType(dict(self.explicit_sources_after)),
        )
        _validate_open_lot_state(self.existing_sources_after, field_name="existing_sources_after")
        for source_transaction_id, state in self.explicit_sources_after.items():
            if not source_transaction_id.strip():
                raise ValueError("Explicit average cost source transaction ID must not be blank")
            _validate_open_lot_state(state, field_name=f"explicit source {source_transaction_id}")
        if self.before.representative_source_transaction_id in self.explicit_sources_after:
            raise ValueError("Existing representative source cannot also be an explicit new source")
        if (
            self.existing_sources_after.quantity > self.before.quantity
            or self.existing_sources_after.cost_local > self.before.cost_local
            or self.existing_sources_after.cost_base > self.before.cost_base
        ):
            raise ValueError("Existing average cost sources cannot increase during a transition")

    @property
    def after(self) -> AverageCostPoolCheckpoint:
        explicit_quantity = sum(
            (state.quantity for state in self.explicit_sources_after.values()), Decimal(0)
        )
        explicit_cost_local = sum(
            (state.cost_local for state in self.explicit_sources_after.values()), Decimal(0)
        )
        explicit_cost_base = sum(
            (state.cost_base for state in self.explicit_sources_after.values()), Decimal(0)
        )
        representative_source_transaction_id = next(
            (
                source_transaction_id
                for source_transaction_id, state in reversed(
                    tuple(self.explicit_sources_after.items())
                )
                if state.quantity > Decimal(0)
            ),
            (
                self.before.representative_source_transaction_id
                if self.existing_sources_after.quantity > Decimal(0)
                else None
            ),
        )
        return AverageCostPoolCheckpoint(
            portfolio_id=self.before.portfolio_id,
            instrument_id=self.before.instrument_id,
            security_id=self.before.security_id,
            representative_source_transaction_id=representative_source_transaction_id,
            quantity=self.existing_sources_after.quantity + explicit_quantity,
            cost_local=self.existing_sources_after.cost_local + explicit_cost_local,
            cost_base=self.existing_sources_after.cost_base + explicit_cost_base,
        )


def _validate_open_lot_state(state: OpenLotState, *, field_name: str) -> None:
    if state.quantity < Decimal(0):
        raise ValueError(f"{field_name} quantity must be nonnegative")
    if state.cost_local < Decimal(0) or state.cost_base < Decimal(0):
        raise ValueError(f"{field_name} basis must be nonnegative")
    if state.quantity == Decimal(0) and (
        state.cost_local != Decimal(0) or state.cost_base != Decimal(0)
    ):
        raise ValueError(f"{field_name} closed quantity must have zero basis")
