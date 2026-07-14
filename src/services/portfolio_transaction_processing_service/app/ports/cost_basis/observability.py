"""Define framework-neutral observation contracts for cost-basis calculations."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self

from ...domain.cost_basis import CostBasisTransaction


class CostBasisCalculationObservation(Protocol):
    """Observe one full-history or incremental cost-basis calculation."""

    def record_depth(self, transaction_count: int) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None: ...


class CostBasisCalculationObserver(Protocol):
    """Create bounded observations without exposing a metrics framework."""

    def observe_recalculation(
        self,
    ) -> AbstractContextManager[CostBasisCalculationObservation]: ...


class CostBasisPersistenceStage(StrEnum):
    """Name one durable state transition in calculated transaction persistence."""

    TRANSACTION_COSTS = "persist_transaction_costs"
    OPEN_LOT = "persist_lot_state"
    ACCRUED_INCOME_OFFSET = "persist_accrued_offset_state"


class CostBasisPersistenceStatus(StrEnum):
    """Describe whether one persistence stage started or completed."""

    ATTEMPT = "attempt"
    SUCCESS = "success"


@dataclass(frozen=True, slots=True)
class CostBasisPersistenceObservation:
    """Describe one cost-basis persistence lifecycle transition."""

    transaction: CostBasisTransaction
    stage: CostBasisPersistenceStage
    status: CostBasisPersistenceStatus


class CostBasisPersistenceObserver(Protocol):
    """Observe persistence without coupling application policy to telemetry."""

    def observe(self, observation: CostBasisPersistenceObservation) -> None: ...
