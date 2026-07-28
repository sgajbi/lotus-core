"""Calculated-output precision policy for durable transaction cashflows."""

from portfolio_common.domain.financial.calculation_precision import CalculatedDecimalPolicy

CASHFLOW_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="cashflow-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)
