"""Define validated average-cost pool checkpoints and transitions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1

from .calculation.lot_state import OpenLotState
from .models.cost_basis_transaction import CostBasisTransaction
from .processing_checkpoint import CostBasisProcessingCheckpoint
from .state_lineage import build_cost_basis_state_lineage

AVERAGE_COST_POOL_STATE_VERSION = "avco-pool-v1"


def _require_nonnegative_finite(value: Decimal, *, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")
    if value < Decimal(0):
        raise ValueError(f"{field_name} must be nonnegative")


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
    calculation_lineage: CalculationLineage | None = None

    def __post_init__(self) -> None:
        _require_nonnegative_finite(
            self.quantity,
            field_name="Average cost pool quantity",
        )
        _require_nonnegative_finite(
            self.cost_local,
            field_name="Average cost pool local basis",
        )
        _require_nonnegative_finite(
            self.cost_base,
            field_name="Average cost pool base basis",
        )
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
        states = tuple(states_by_source_transaction_id.values())
        quantity = _sum_state_field(states, field_name="quantity")
        cost_local = _sum_state_field(states, field_name="cost_local")
        cost_base = _sum_state_field(states, field_name="cost_base")
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
            original_quantity=self.quantity,
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
        explicit_states = tuple(self.explicit_sources_after.values())
        explicit_quantity = _sum_state_field(explicit_states, field_name="quantity")
        explicit_cost_local = _sum_state_field(explicit_states, field_name="cost_local")
        explicit_cost_base = _sum_state_field(explicit_states, field_name="cost_base")
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
            quantity=COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                self.existing_sources_after.quantity,
                explicit_quantity,
                field_name="pool_quantity",
            ),
            cost_local=COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                self.existing_sources_after.cost_local,
                explicit_cost_local,
                field_name="pool_cost_local",
            ),
            cost_base=COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
                self.existing_sources_after.cost_base,
                explicit_cost_base,
                field_name="pool_cost_base",
            ),
        )


@dataclass(frozen=True, slots=True)
class AverageCostPoolRebuildPlan:
    checkpoint: AverageCostPoolCheckpoint
    processing_checkpoint: CostBasisProcessingCheckpoint
    replay_lineage: CalculationLineage
    source_transactions: tuple[CostBasisTransaction, ...]
    source_states: Mapping[str, OpenLotState]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_states", MappingProxyType(dict(self.source_states)))
        if not isinstance(self.replay_lineage, CalculationLineage):
            raise ValueError("Average cost rebuild requires typed replay lineage")
        if (
            self.processing_checkpoint.portfolio_id != self.checkpoint.portfolio_id
            or self.processing_checkpoint.security_id != self.checkpoint.security_id
            or self.processing_checkpoint.cost_basis_method != CostBasisMethod.AVCO.value
        ):
            raise ValueError("Average cost rebuild processing checkpoint is incompatible")
        source_transaction_ids = {
            transaction.transaction_id for transaction in self.source_transactions
        }
        if len(source_transaction_ids) != len(self.source_transactions):
            raise ValueError("Average cost rebuild source transactions must be unique")
        missing_source_ids = set(self.source_states) - source_transaction_ids
        if missing_source_ids:
            raise ValueError("Average cost rebuild state has no source transaction")
        if any(
            transaction.portfolio_id != self.checkpoint.portfolio_id
            or transaction.security_id != self.checkpoint.security_id
            for transaction in self.source_transactions
        ):
            raise ValueError("Average cost rebuild source transaction is outside the pool key")

        expected_checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
            portfolio_id=self.checkpoint.portfolio_id,
            instrument_id=self.checkpoint.instrument_id,
            security_id=self.checkpoint.security_id,
            states_by_source_transaction_id=self.source_states,
        )
        if expected_checkpoint != self.checkpoint:
            raise ValueError("Average cost rebuild checkpoint does not match source state")


def build_average_cost_pool_rebuild_lineage(
    *,
    replay_lineage: CalculationLineage,
    checkpoint: AverageCostPoolCheckpoint,
) -> CalculationLineage:
    """Bind an authoritative replay receipt to its deterministic replacement checkpoint."""

    return build_cost_basis_state_lineage(
        algorithm_id="average-cost-pool-rebuild",
        input_payload={"replay_lineage": replay_lineage.lineage_payload()},
        output_payload={
            "calculation_lineage": None,
            "cost_base": checkpoint.cost_base,
            "cost_local": checkpoint.cost_local,
            "instrument_id": checkpoint.instrument_id,
            "portfolio_id": checkpoint.portfolio_id,
            "quantity": checkpoint.quantity,
            "representative_source_transaction_id": (
                checkpoint.representative_source_transaction_id
            ),
            "security_id": checkpoint.security_id,
            "state_version": checkpoint.state_version,
        },
    )


def _validate_open_lot_state(state: OpenLotState, *, field_name: str) -> None:
    _require_nonnegative_finite(
        state.quantity,
        field_name=f"{field_name} quantity",
    )
    _require_nonnegative_finite(
        state.cost_local,
        field_name=f"{field_name} local basis",
    )
    _require_nonnegative_finite(
        state.cost_base,
        field_name=f"{field_name} base basis",
    )
    if state.quantity == Decimal(0) and (
        state.cost_local != Decimal(0) or state.cost_base != Decimal(0)
    ):
        raise ValueError(f"{field_name} closed quantity must have zero basis")


def _sum_state_field(
    states: tuple[OpenLotState, ...],
    *,
    field_name: str,
) -> Decimal:
    total = Decimal(0)
    for state in states:
        total = COST_BASIS_STATE_LEDGER_OUTPUT_V1.add(
            total,
            getattr(state, field_name),
            field_name=f"pool_{field_name}",
        )
    return total
