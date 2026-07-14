"""Define observability emitted after deterministic cashflow calculation."""

from typing import Protocol

from ...domain.cashflow import CalculatedCashflow


class CashflowCalculationObserver(Protocol):
    """Observe one successfully calculated transaction cashflow."""

    def calculated(self, cashflow: CalculatedCashflow) -> None: ...
