"""Test the Prometheus adapter for cost-basis calculation observations."""

from unittest.mock import MagicMock

from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PrometheusCostBasisCalculationObserver,
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
