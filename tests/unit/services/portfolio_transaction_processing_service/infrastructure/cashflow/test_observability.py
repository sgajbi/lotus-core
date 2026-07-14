"""Test cashflow calculation metric and log observation."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    PrometheusCashflowCalculationObserver,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    observability as observability_module,
)


def test_observer_increments_bounded_cashflow_metric(monkeypatch) -> None:
    metric = MagicMock()
    monkeypatch.setattr(observability_module, "CASHFLOWS_CREATED_TOTAL", metric)
    cashflow = CalculatedCashflow(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 4, 12),
        epoch=3,
        amount=Decimal("-252"),
        currency="SGD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=None,
        linked_transaction_group_id=None,
    )

    PrometheusCashflowCalculationObserver().calculated(cashflow)

    metric.labels.assert_called_once_with(
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
    )
    metric.labels.return_value.inc.assert_called_once_with()
