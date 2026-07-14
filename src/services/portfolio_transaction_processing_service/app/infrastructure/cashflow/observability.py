"""Emit bounded Prometheus and structured-log cashflow calculation evidence."""

import logging

from portfolio_common.monitoring import CASHFLOWS_CREATED_TOTAL

from ...domain.cashflow import CalculatedCashflow

logger = logging.getLogger(__name__)


class PrometheusCashflowCalculationObserver:
    """Observe successful calculations with bounded financial labels."""

    def calculated(self, cashflow: CalculatedCashflow) -> None:
        CASHFLOWS_CREATED_TOTAL.labels(
            classification=cashflow.classification,
            timing=cashflow.timing,
        ).inc()
        logger.info(
            "Calculated cashflow for transaction %s: amount=%s classification=%s",
            cashflow.transaction_id,
            cashflow.amount,
            cashflow.classification,
        )


PROMETHEUS_CASHFLOW_CALCULATION_OBSERVER = PrometheusCashflowCalculationObserver()
