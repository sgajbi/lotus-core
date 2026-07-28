"""Exact persistence policy for generic simulation change economics."""

from __future__ import annotations

from decimal import Decimal

from portfolio_common.domain.financial.precision import DecimalPrecisionPolicy

SIMULATION_CHANGE_PERSISTENCE_PRECISION_V1 = DecimalPrecisionPolicy(
    name="simulation-change-persistence-v1",
    precision=18,
    scale=10,
)


def require_exact_simulation_change_values(
    *,
    quantity: Decimal | None,
    price: Decimal | None,
    amount: Decimal | None,
) -> None:
    """Defend the application boundary when callers bypass the HTTP contract."""

    for field_name, value in (
        ("quantity", quantity),
        ("price", price),
        ("amount", amount),
    ):
        if value is None:
            continue
        SIMULATION_CHANGE_PERSISTENCE_PRECISION_V1.require_exact(
            value,
            field_name=field_name,
        )
    if price is not None and price <= Decimal(0):
        raise ValueError("price must be greater than zero")
