"""Calculated-output precision policy for durable position history."""

from portfolio_common.domain.financial.calculation_precision import CalculatedDecimalPolicy

POSITION_HISTORY_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="position-history-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)
