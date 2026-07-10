from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from types import TracebackType

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

from ..ports import (
    TransactionProcessingObservation,
    TransactionProcessingObserver,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
)

logger = logging.getLogger(__name__)

_DURATION_BUCKETS_SECONDS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)


class PrometheusTransactionProcessingObserver(TransactionProcessingObserver):
    def __init__(
        self,
        *,
        registry: CollectorRegistry = REGISTRY,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._clock = clock
        self._operations = Counter(
            "lotus_core_transaction_processing_operations_total",
            "Completed transaction processing operations by bounded outcome.",
            labelnames=("stage", "outcome"),
            registry=registry,
        )
        self._duration = Histogram(
            "lotus_core_transaction_processing_operation_duration_seconds",
            "Transaction processing operation duration by bounded outcome.",
            labelnames=("stage", "outcome"),
            buckets=_DURATION_BUCKETS_SECONDS,
            registry=registry,
        )

    def observe(
        self,
        operation: TransactionProcessingOperation,
    ) -> TransactionProcessingObservation:
        return _PrometheusTransactionProcessingObservation(
            operation=operation,
            operations=self._operations,
            duration=self._duration,
            clock=self._clock,
        )


class _PrometheusTransactionProcessingObservation(TransactionProcessingObservation):
    def __init__(
        self,
        *,
        operation: TransactionProcessingOperation,
        operations: Counter,
        duration: Histogram,
        clock: Callable[[], float],
    ) -> None:
        self._operation = operation
        self._operations = operations
        self._duration = duration
        self._clock = clock
        self._started_at = 0.0
        self._outcome = TransactionProcessingOutcome.SUCCEEDED

    def set_outcome(self, outcome: TransactionProcessingOutcome) -> None:
        self._outcome = outcome

    def __enter__(self) -> _PrometheusTransactionProcessingObservation:
        self._started_at = self._clock()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None and self._outcome is TransactionProcessingOutcome.SUCCEEDED:
            self._outcome = TransactionProcessingOutcome.FAILED
        elapsed_seconds = max(self._clock() - self._started_at, 0.0)
        try:
            labels = {
                "stage": self._operation.value,
                "outcome": self._outcome.value,
            }
            self._operations.labels(**labels).inc()
            self._duration.labels(**labels).observe(elapsed_seconds)
        except Exception:
            logger.exception(
                "Transaction processing metric recording failed.",
                extra={"operation": self._operation.value},
            )


PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER = PrometheusTransactionProcessingObserver()
