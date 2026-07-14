"""Adapt cost-basis calculation observations to the existing Prometheus metrics."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from types import TracebackType

from prometheus_client import Histogram

from ...ports.cost_basis.observability import (
    CostBasisCalculationObservation,
    CostBasisCalculationObserver,
)
from .metrics import (
    RECALCULATION_DEPTH,
    RECALCULATION_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)


class PrometheusCostBasisCalculationObserver(CostBasisCalculationObserver):
    """Record calculation depth and duration through injected Prometheus histograms."""

    def __init__(
        self,
        *,
        depth: Histogram = RECALCULATION_DEPTH,
        duration: Histogram = RECALCULATION_DURATION_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._depth = depth
        self._duration = duration
        self._clock = clock

    def observe_recalculation(self) -> CostBasisCalculationObservation:
        return _PrometheusCostBasisCalculationObservation(
            depth=self._depth,
            duration=self._duration,
            clock=self._clock,
        )


class _PrometheusCostBasisCalculationObservation(CostBasisCalculationObservation):
    def __init__(
        self,
        *,
        depth: Histogram,
        duration: Histogram,
        clock: Callable[[], float],
    ) -> None:
        self._depth = depth
        self._duration = duration
        self._clock = clock
        self._started_at = 0.0

    def record_depth(self, transaction_count: int) -> None:
        try:
            self._depth.observe(transaction_count)
        except Exception:
            logger.exception("Cost-basis recalculation depth metric recording failed.")

    def __enter__(self) -> _PrometheusCostBasisCalculationObservation:
        self._started_at = self._clock()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        elapsed_seconds = max(self._clock() - self._started_at, 0.0)
        try:
            self._duration.observe(elapsed_seconds)
        except Exception:
            logger.exception("Cost-basis recalculation duration metric recording failed.")


PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER = PrometheusCostBasisCalculationObserver()
