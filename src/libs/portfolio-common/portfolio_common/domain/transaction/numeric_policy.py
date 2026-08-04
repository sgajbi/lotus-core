"""Precision policy for transaction values that cross the persistence boundary."""

from __future__ import annotations

from decimal import Decimal

from portfolio_common.domain.financial.calculation_precision import CalculatedDecimalPolicy
from portfolio_common.domain.financial.precision import DecimalPrecisionPolicy
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS

TRANSACTION_PERSISTENCE_PRECISION_V1 = DecimalPrecisionPolicy(
    name="transaction-persistence-v1",
    precision=18,
    scale=10,
)
TRANSACTION_COST_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="transaction-cost-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)
COST_BASIS_STATE_LEDGER_OUTPUT_V1 = CalculatedDecimalPolicy(
    name="cost-basis-state-ledger-output",
    version="1.0.0",
    precision=18,
    scale=10,
)

TRANSACTION_COMMAND_DECIMAL_FIELDS = (
    "quantity",
    "price",
    "gross_transaction_amount",
    "transaction_fx_rate",
    "trade_fee",
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
    "withholding_tax_amount",
    "other_interest_deductions_amount",
    "net_interest_amount",
    "buy_amount",
    "sell_amount",
    "contract_rate",
    "allocated_cost_basis_local",
    "allocated_cost_basis_base",
    "realized_capital_pnl_local",
    "realized_fx_pnl_local",
    "realized_total_pnl_local",
    "realized_capital_pnl_base",
    "realized_fx_pnl_base",
    "realized_total_pnl_base",
    "old_factor",
    "new_factor",
    "principal_proceeds_local",
    "accrued_interest_proceeds_local",
    "embedded_fee_amount_local",
    "embedded_tax_amount_local",
    "synthetic_flow_amount_local",
    "synthetic_flow_amount_base",
    "synthetic_flow_fx_rate_to_base",
    "synthetic_flow_price_used",
    "synthetic_flow_quantity_used",
)

TRANSACTION_CALCULATED_DECIMAL_FIELDS = (
    "gross_cost",
    "net_cost",
    "realized_gain_loss",
    "net_cost_local",
    "realized_gain_loss_local",
)

TRANSACTION_EVENT_DECIMAL_FIELDS = (
    *TRANSACTION_COMMAND_DECIMAL_FIELDS,
    *TRANSACTION_CALCULATED_DECIMAL_FIELDS,
)

TRANSACTION_PERSISTED_DECIMAL_FIELDS = tuple(
    field_name
    for field_name in TRANSACTION_EVENT_DECIMAL_FIELDS
    if field_name not in TRANSACTION_FEE_COMPONENT_FIELDS
)


def require_transaction_persistence_precision(
    value: Decimal | None,
    *,
    field_name: str,
) -> Decimal | None:
    """Reject a value that cannot be persisted exactly by the transaction ledger."""

    if value is None:
        return None
    return TRANSACTION_PERSISTENCE_PRECISION_V1.require_exact(
        value,
        field_name=field_name,
    )
