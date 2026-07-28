"""Enforce finite reference-data and market-series numeric boundaries.

Revision ID: c122b2c3d4fb
Revises: c121b2c3d4fa
Create Date: 2026-07-28 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c122b2c3d4fb"
down_revision: str | Sequence[str] | None = "c121b2c3d4fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "fx_rates",
        "ck_fx_rates_rate_finite",
        "CAST(rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    ("fx_rates", "ck_fx_rates_rate_positive", "rate > 0"),
    (
        "market_prices",
        "ck_market_prices_price_finite",
        "CAST(price AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    ("market_prices", "ck_market_prices_price_positive", "price > 0"),
    (
        "instruments",
        "ck_instruments_fx_terms_finite",
        "CAST(buy_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(sell_amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(contract_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "instruments",
        "ck_instruments_fx_terms_positive",
        "buy_amount > 0 AND sell_amount > 0 AND contract_rate > 0",
    ),
    (
        "benchmark_composition_series",
        "ck_benchmark_composition_weight_finite",
        "CAST(composition_weight AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "benchmark_composition_series",
        "ck_benchmark_composition_weight_nonnegative",
        "composition_weight >= 0",
    ),
    (
        "index_price_series",
        "ck_index_price_series_price_finite",
        "CAST(index_price AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "index_price_series",
        "ck_index_price_series_price_positive",
        "index_price > 0",
    ),
    (
        "index_return_series",
        "ck_index_return_series_return_finite",
        "CAST(index_return AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "benchmark_return_series",
        "ck_benchmark_return_series_return_finite",
        "CAST(benchmark_return AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "risk_free_series",
        "ck_risk_free_series_value_finite",
        "CAST(value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "instrument_lookthrough_components",
        "ck_instrument_lookthrough_weight_finite",
        "CAST(component_weight AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "instrument_lookthrough_components",
        "ck_instrument_lookthrough_weight_nonnegative",
        "component_weight >= 0",
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
    """Block new invalid writes before validating retained reference facts."""

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
