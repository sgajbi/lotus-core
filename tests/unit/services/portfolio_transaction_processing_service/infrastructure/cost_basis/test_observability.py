"""Test cost-basis calculation and persistence observability adapters."""

import logging
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.observability import (  # noqa: E501
    PrometheusCostBasisCalculationObserver,
    PrometheusCostBasisPersistenceObserver,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisExecutionMode,
    CostBasisPersistenceObservation,
    CostBasisPersistenceStage,
    CostBasisPersistenceStatus,
)


def test_prometheus_cost_basis_observer_records_depth_and_duration() -> None:
    depth = MagicMock()
    duration = MagicMock()
    clock = MagicMock(side_effect=[10.0, 10.25])
    observer = PrometheusCostBasisCalculationObserver(
        depth=depth,
        duration=duration,
        clock=clock,
    )

    with observer.observe_recalculation() as observation:
        observation.record_depth(17)

    depth.observe.assert_called_once_with(17)
    duration.observe.assert_called_once_with(0.25)


def test_prometheus_cost_basis_observer_records_execution_and_restored_lots() -> None:
    execution = MagicMock()
    restored_open_lots = MagicMock()
    observer = PrometheusCostBasisCalculationObserver(
        execution=execution,
        restored_open_lots=restored_open_lots,
    )

    observer.record_execution(CostBasisExecutionMode.ORDERED_APPEND, "AVCO")
    observer.record_restored_open_lots(cost_basis_method="AVCO", lot_count=7)

    execution.labels.assert_called_once_with(mode="ordered_append", cost_basis_method="AVCO")
    execution.labels.return_value.inc.assert_called_once_with()
    restored_open_lots.labels.assert_called_once_with(cost_basis_method="AVCO")
    restored_open_lots.labels.return_value.observe.assert_called_once_with(7)


def test_prometheus_cost_basis_execution_observation_contains_metric_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    execution = MagicMock()
    execution.labels.side_effect = RuntimeError("metrics unavailable")
    observer = PrometheusCostBasisCalculationObserver(execution=execution)

    with caplog.at_level(logging.ERROR):
        observer.record_execution(CostBasisExecutionMode.FULL_REBUILD, "FIFO")

    assert "Cost-basis execution metric recording failed." in caplog.messages


def _persistence_observation(
    *,
    transaction_type: str,
    stage: CostBasisPersistenceStage,
    status: CostBasisPersistenceStatus = CostBasisPersistenceStatus.SUCCESS,
) -> CostBasisPersistenceObservation:
    return CostBasisPersistenceObservation(
        transaction=CostBasisTransaction(
            transaction_id=f"{transaction_type}-OBS-1",
            portfolio_id="PORT-1",
            instrument_id="INST-1",
            security_id="SEC-1",
            transaction_type=transaction_type,
            transaction_date=datetime(2026, 1, 2),
            quantity=Decimal("4"),
            gross_transaction_amount=Decimal("48"),
            trade_currency="USD",
            portfolio_base_currency="USD",
            economic_event_id="ECON-1",
            linked_transaction_group_id="GROUP-1",
            calculation_policy_id="POLICY-1",
            calculation_policy_version="1",
        ),
        stage=stage,
        status=status,
    )


@pytest.mark.parametrize(
    ("transaction_type", "stage", "expected_log_event"),
    [
        ("BUY", CostBasisPersistenceStage.OPEN_LOT, "open_lot_state_persisted"),
        ("SELL", CostBasisPersistenceStage.TRANSACTION_COSTS, "sell_state_persisted"),
    ],
)
def test_prometheus_persistence_observer_preserves_metrics_and_support_logs(
    transaction_type: str,
    stage: CostBasisPersistenceStage,
    expected_log_event: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    buy_lifecycle = MagicMock()
    sell_lifecycle = MagicMock()
    observer = PrometheusCostBasisPersistenceObserver(
        buy_lifecycle=buy_lifecycle,
        sell_lifecycle=sell_lifecycle,
    )
    observation = _persistence_observation(
        transaction_type=transaction_type,
        stage=stage,
    )

    with caplog.at_level(logging.DEBUG):
        observer.observe(observation)

    selected_counter = buy_lifecycle if transaction_type == "BUY" else sell_lifecycle
    selected_counter.labels.assert_called_once_with(stage.value, "success")
    selected_counter.labels.return_value.inc.assert_called_once_with()
    assert expected_log_event in caplog.messages


def test_persistence_observer_contains_telemetry_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    buy_lifecycle = MagicMock()
    buy_lifecycle.labels.side_effect = RuntimeError("metrics unavailable")
    observer = PrometheusCostBasisPersistenceObserver(
        buy_lifecycle=buy_lifecycle,
        sell_lifecycle=MagicMock(),
    )

    with caplog.at_level(logging.ERROR):
        observer.observe(
            _persistence_observation(
                transaction_type="BUY",
                stage=CostBasisPersistenceStage.TRANSACTION_COSTS,
            )
        )

    assert "Cost-basis persistence observation failed." in caplog.messages
