"""Enforce finite transaction-economics and cashflow numeric boundaries.

Revision ID: c125b2c3d4fe
Revises: c124b2c3d4fd
Create Date: 2026-07-28 18:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c125b2c3d4fe"
down_revision: str | Sequence[str] | None = "c124b2c3d4fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "transactions",
        "ck_transactions_trade_values_finite",
        "CAST(price AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(gross_transaction_amount AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(trade_fee AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(gross_cost AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(net_cost AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_gain_loss AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(transaction_fx_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(net_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_gain_loss_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_trade_values_sign",
        "price >= 0 AND gross_transaction_amount >= 0 AND trade_fee >= 0 "
        "AND transaction_fx_rate > 0",
    ),
    (
        "transactions",
        "ck_transactions_income_values_finite",
        "CAST(withholding_tax_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(other_interest_deductions_amount AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(net_interest_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_income_values_nonnegative",
        "withholding_tax_amount >= 0 AND other_interest_deductions_amount >= 0 "
        "AND net_interest_amount >= 0",
    ),
    (
        "transactions",
        "ck_transactions_fx_terms_finite",
        "CAST(buy_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(sell_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(contract_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_fx_terms_positive",
        "buy_amount > 0 AND sell_amount > 0 AND contract_rate > 0",
    ),
    (
        "transactions",
        "ck_transactions_realized_values_finite",
        "CAST(allocated_cost_basis_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(allocated_cost_basis_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_capital_pnl_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_fx_pnl_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_total_pnl_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_capital_pnl_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_fx_pnl_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(realized_total_pnl_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_allocated_basis_nonnegative",
        "allocated_cost_basis_local >= 0 AND allocated_cost_basis_base >= 0",
    ),
    (
        "transactions",
        "ck_transactions_synthetic_flow_values_finite",
        "CAST(synthetic_flow_amount_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(synthetic_flow_amount_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(synthetic_flow_fx_rate_to_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(synthetic_flow_price_used AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(synthetic_flow_quantity_used AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_synthetic_flow_values_sign",
        "synthetic_flow_fx_rate_to_base > 0 AND synthetic_flow_price_used >= 0 "
        "AND synthetic_flow_quantity_used >= 0",
    ),
    (
        "cashflows",
        "ck_cashflows_amount_finite",
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
)


def _validation_statements() -> tuple[str, ...]:
    grouped: dict[str, list[str]] = {}
    for table_name, constraint_name, _ in _CONSTRAINTS:
        grouped.setdefault(table_name, []).append(constraint_name)
    return tuple(
        f'ALTER TABLE "{table_name}" '
        + ", ".join(
            f'VALIDATE CONSTRAINT "{constraint_name}"' for constraint_name in constraint_names
        )
        for table_name, constraint_names in grouped.items()
    )


def upgrade() -> None:
    """Block new invalid writes before validating retained transaction facts."""

    for table_name, constraint_name, condition in _CONSTRAINTS:
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
            postgresql_not_valid=True,
        )
    for statement in _validation_statements():
        op.execute(statement)


def downgrade() -> None:
    for table_name, constraint_name, _ in reversed(_CONSTRAINTS):
        op.drop_constraint(constraint_name, table_name, type_="check")
