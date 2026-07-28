"""Numeric output policy for persisted position-timeseries calculations."""

from portfolio_common.domain.financial.calculation_precision import (
    CalculatedDecimalPolicy,
)

POSITION_TIMESERIES_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="position-timeseries-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)
