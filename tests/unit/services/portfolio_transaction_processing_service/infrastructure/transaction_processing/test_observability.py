from __future__ import annotations

from collections.abc import Iterator

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_processing import (  # noqa: E501
    PrometheusTransactionProcessingObserver,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
)


def _clock(values: Iterator[float]):
    return lambda: next(values)


def test_observer_records_bounded_success_rejection_and_failure_metrics() -> None:
    registry = CollectorRegistry()
    observer = PrometheusTransactionProcessingObserver(
        registry=registry,
        clock=_clock(iter((10.0, 10.25, 20.0, 20.5, 30.0, 31.0))),
    )

    with observer.observe(TransactionProcessingOperation.COST):
        pass
    with observer.observe(TransactionProcessingOperation.CASHFLOW) as observation:
        observation.set_outcome(TransactionProcessingOutcome.REJECTED)
    with pytest.raises(RuntimeError, match="position failed"):
        with observer.observe(TransactionProcessingOperation.POSITION):
            raise RuntimeError("position failed")

    metrics = generate_latest(registry).decode("utf-8")
    assert (
        "lotus_core_transaction_processing_operations_total"
        '{outcome="succeeded",stage="cost"} 1.0' in metrics
    )
    assert (
        "lotus_core_transaction_processing_operations_total"
        '{outcome="rejected",stage="cashflow"} 1.0' in metrics
    )
    assert (
        "lotus_core_transaction_processing_operations_total"
        '{outcome="failed",stage="position"} 1.0' in metrics
    )
    assert (
        "lotus_core_transaction_processing_operation_duration_seconds_sum"
        '{outcome="succeeded",stage="cost"} 0.25' in metrics
    )
