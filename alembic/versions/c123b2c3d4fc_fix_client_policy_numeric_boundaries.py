"""Enforce finite client-policy and model-weight numeric boundaries.

Revision ID: c123b2c3d4fc
Revises: c122b2c3d4fb
Create Date: 2026-07-28 18:10:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c123b2c3d4fc"
down_revision: str | Sequence[str] | None = "c122b2c3d4fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "sustainability_preference_profiles",
        "ck_sustainability_allocations_finite",
        "CAST(minimum_allocation AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(maximum_allocation AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "sustainability_preference_profiles",
        "ck_sustainability_allocations_nonnegative",
        "minimum_allocation >= 0 AND maximum_allocation >= 0",
    ),
    (
        "client_tax_profiles",
        "ck_client_tax_withholding_rate_finite",
        "CAST(withholding_tax_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "client_tax_profiles",
        "ck_client_tax_withholding_rate_nonnegative",
        "withholding_tax_rate >= 0",
    ),
    (
        "client_tax_rule_sets",
        "ck_client_tax_rule_values_finite",
        "CAST(rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(threshold_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "client_tax_rule_sets",
        "ck_client_tax_rule_values_nonnegative",
        "rate >= 0 AND threshold_amount >= 0",
    ),
    (
        "client_income_needs_schedules",
        "ck_client_income_need_amount_finite",
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "client_income_needs_schedules",
        "ck_client_income_need_amount_positive",
        "amount > 0",
    ),
    (
        "liquidity_reserve_requirements",
        "ck_liquidity_reserve_amount_finite",
        "CAST(required_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "liquidity_reserve_requirements",
        "ck_liquidity_reserve_amount_positive",
        "required_amount > 0",
    ),
    (
        "planned_withdrawal_schedules",
        "ck_planned_withdrawal_amount_finite",
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "planned_withdrawal_schedules",
        "ck_planned_withdrawal_amount_positive",
        "amount > 0",
    ),
    (
        "model_portfolio_targets",
        "ck_model_portfolio_weights_finite",
        "CAST(target_weight AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(min_weight AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(max_weight AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "model_portfolio_targets",
        "ck_model_portfolio_weights_nonnegative",
        "target_weight >= 0 AND min_weight >= 0 AND max_weight >= 0",
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
    """Block new invalid writes before validating retained client-policy facts."""

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
