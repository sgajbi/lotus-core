"""Single-statement transaction-cost snapshot expressions for read adapters."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from portfolio_common.database_models import TransactionCost


@dataclass(frozen=True, slots=True)
class TransactionCostSnapshot:
    """One transaction-cost row reconstructed from aligned aggregate columns."""

    fee_type: str
    amount: Decimal
    currency: str
    updated_at: datetime | None


def transaction_cost_snapshot_lateral(transaction_id: Any):
    """Return one lateral aggregate row for the supplied transaction identity."""

    return (
        select(
            func.array_agg(
                aggregate_order_by(TransactionCost.fee_type, TransactionCost.id.asc())
            ).label("cost_fee_types"),
            func.array_agg(
                aggregate_order_by(TransactionCost.amount, TransactionCost.id.asc())
            ).label("cost_amounts"),
            func.array_agg(
                aggregate_order_by(TransactionCost.currency, TransactionCost.id.asc())
            ).label("cost_currencies"),
            func.array_agg(
                aggregate_order_by(TransactionCost.updated_at, TransactionCost.id.asc())
            ).label("cost_updated_ats"),
        )
        .where(TransactionCost.transaction_id == transaction_id)
        .correlate_except(TransactionCost)
        .lateral("transaction_cost_snapshot")
    )


def transaction_cost_snapshots(
    *,
    fee_types: list[str] | None,
    amounts: list[Decimal] | None,
    currencies: list[str] | None,
    updated_ats: list[datetime] | None,
) -> tuple[TransactionCostSnapshot, ...]:
    """Reconstruct ordered costs and fail closed if aggregate columns diverge."""

    if fee_types is None and amounts is None and currencies is None and updated_ats is None:
        return ()
    if fee_types is None or amounts is None or currencies is None or updated_ats is None:
        raise ValueError("Transaction-cost snapshot aggregates must be null together.")
    component_count = len(fee_types)
    if not (
        len(amounts) == component_count
        and len(currencies) == component_count
        and len(updated_ats) == component_count
    ):
        raise ValueError("Transaction-cost snapshot aggregate lengths must match.")
    return tuple(
        TransactionCostSnapshot(
            fee_type=fee_types[index],
            amount=amounts[index],
            currency=currencies[index],
            updated_at=updated_ats[index],
        )
        for index in range(component_count)
    )
