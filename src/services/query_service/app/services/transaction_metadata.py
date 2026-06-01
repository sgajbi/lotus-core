from datetime import datetime
from typing import cast

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN


def ledger_data_quality_status(
    *,
    total_count: int,
    returned_count: int,
    skip: int,
) -> str:
    if total_count <= 0:
        return cast(str, UNKNOWN)
    if skip > 0 or returned_count < total_count:
        return cast(str, PARTIAL)
    return cast(str, COMPLETE)


def latest_transaction_evidence_timestamp(transactions: list[object]) -> datetime | None:
    return max(
        (
            updated_at
            for transaction in transactions
            if (updated_at := getattr(transaction, "updated_at", None)) is not None
        ),
        default=None,
    )
