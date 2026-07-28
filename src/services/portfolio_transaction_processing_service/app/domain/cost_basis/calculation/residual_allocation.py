"""Residual-safe apportionment for persisted cost-basis state."""

from decimal import Decimal
from typing import cast

from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)


def allocate_nonnegative_storage_share(
    candidate: Decimal,
    *,
    aggregate: Decimal,
    allocated: Decimal,
    field_name: str,
) -> Decimal:
    """Normalize one share without consuming more than the aggregate residual."""

    normalized = cast(
        Decimal,
        COST_BASIS_STATE_LEDGER_OUTPUT_V1.normalize(
            candidate,
            field_name=field_name,
        ),
    )
    unallocated = cast(
        Decimal,
        COST_BASIS_STATE_LEDGER_OUTPUT_V1.subtract(
            aggregate,
            allocated,
            field_name=f"unallocated_{field_name}",
        ),
    )
    if normalized < Decimal(0) or unallocated < Decimal(0):
        raise ValueError(f"{field_name} allocation must not be negative")
    return min(normalized, unallocated)
