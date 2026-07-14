"""Adapt cost-basis observations to Prometheus metrics and support logs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from types import TracebackType

from portfolio_common.monitoring import BUY_LIFECYCLE_STAGE_TOTAL, SELL_LIFECYCLE_STAGE_TOTAL
from prometheus_client import Counter, Histogram

from ...ports.cost_basis.observability import (
    CostBasisCalculationObservation,
    CostBasisCalculationObserver,
    CostBasisPersistenceObservation,
    CostBasisPersistenceStage,
    CostBasisPersistenceStatus,
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


class PrometheusCostBasisPersistenceObserver:
    """Record cost-basis writes without allowing telemetry failures to abort them."""

    def __init__(
        self,
        *,
        buy_lifecycle: Counter = BUY_LIFECYCLE_STAGE_TOTAL,
        sell_lifecycle: Counter = SELL_LIFECYCLE_STAGE_TOTAL,
    ) -> None:
        self._buy_lifecycle = buy_lifecycle
        self._sell_lifecycle = sell_lifecycle

    def observe(self, observation: CostBasisPersistenceObservation) -> None:
        """Record one persistence transition through stable lifecycle vocabulary."""

        try:
            self._record(observation)
        except Exception:
            logger.exception(
                "Cost-basis persistence observation failed.",
                extra={
                    "transaction_id": observation.transaction.transaction_id,
                    "cost_basis_persistence_stage": observation.stage.value,
                    "cost_basis_persistence_status": observation.status.value,
                },
            )

    def _record(self, observation: CostBasisPersistenceObservation) -> None:
        transaction_type = observation.transaction.transaction_type.strip().upper()
        counter = {
            "BUY": self._buy_lifecycle,
            "SELL": self._sell_lifecycle,
        }.get(transaction_type)
        if counter is not None:
            counter.labels(observation.stage.value, observation.status.value).inc()

        if observation.status is not CostBasisPersistenceStatus.SUCCESS:
            return
        if observation.stage is CostBasisPersistenceStage.OPEN_LOT:
            _log_persisted_transaction_state(
                "open_lot_state_persisted",
                observation,
            )
        if (
            observation.stage is CostBasisPersistenceStage.TRANSACTION_COSTS
            and transaction_type == "SELL"
        ):
            _log_persisted_transaction_state("sell_state_persisted", observation)


def _log_persisted_transaction_state(
    event_name: str,
    observation: CostBasisPersistenceObservation,
) -> None:
    transaction = observation.transaction
    logger.info(
        event_name,
        extra={
            "transaction_id": transaction.transaction_id,
            "economic_event_id": getattr(transaction, "economic_event_id", None),
            "linked_transaction_group_id": getattr(
                transaction,
                "linked_transaction_group_id",
                None,
            ),
            "calculation_policy_id": getattr(transaction, "calculation_policy_id", None),
            "calculation_policy_version": getattr(
                transaction,
                "calculation_policy_version",
                None,
            ),
        },
    )


PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER = PrometheusCostBasisPersistenceObserver()
