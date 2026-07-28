"""Numeric output policy for persisted position valuation results."""

from portfolio_common.domain.financial.calculation_precision import (
    CalculatedDecimalPolicy,
)

POSITION_VALUATION_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="position-valuation-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)
