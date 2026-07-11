"""Evidence timestamp policies for transaction-economics source products."""

from datetime import datetime

from ...domain.transaction_economics import BookedTransactionEconomics


def latest_evidence_timestamp(rows: list[BookedTransactionEconomics]) -> datetime | None:
    """Return the latest transaction, cost, or cashflow evidence timestamp."""

    timestamps: list[datetime] = []
    for row in rows:
        if row.updated_at is not None:
            timestamps.append(row.updated_at)
        if row.cashflow is not None and row.cashflow.updated_at is not None:
            timestamps.append(row.cashflow.updated_at)
        timestamps.extend(cost.updated_at for cost in row.costs if cost.updated_at is not None)
    return max(timestamps, default=None)
