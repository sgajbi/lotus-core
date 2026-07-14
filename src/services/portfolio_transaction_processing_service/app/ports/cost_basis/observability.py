"""Define framework-neutral observation contracts for cost-basis calculations."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Protocol, Self


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
