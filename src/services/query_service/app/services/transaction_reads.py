from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .transaction_metadata import latest_transaction_evidence_timestamp


@dataclass(frozen=True)
class TransactionLedgerPage:
    total_count: int
    rows: list[Any]
    latest_evidence_timestamp: datetime | None


@dataclass(frozen=True)
class RealizedTaxEvidenceRead:
    source_transaction_count: int
    tax_transactions: list[Any]
    latest_evidence_timestamp: datetime | None


async def read_transaction_ledger_page(
    *,
    repository: Any,
    ledger_filters: dict[str, Any],
    skip: int,
    limit: int,
    sort_by: str | None,
    sort_order: str | None,
) -> TransactionLedgerPage:
    total_count = await repository.get_transactions_count(**ledger_filters)
    if total_count == 0:
        return TransactionLedgerPage(
            total_count=0,
            rows=[],
            latest_evidence_timestamp=None,
        )

    rows = await repository.get_transactions(
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        **ledger_filters,
    )

    if skip > 0 or limit < total_count or len(rows) != total_count:
        latest_evidence_timestamp = await repository.get_latest_evidence_timestamp(**ledger_filters)
    else:
        latest_evidence_timestamp = latest_transaction_evidence_timestamp(rows)

    return TransactionLedgerPage(
        total_count=total_count,
        rows=rows,
        latest_evidence_timestamp=latest_evidence_timestamp,
    )


async def read_realized_tax_evidence(
    *,
    repository: Any,
    ledger_filters: dict[str, Any],
) -> RealizedTaxEvidenceRead:
    source_transaction_count = await repository.get_transactions_count(**ledger_filters)
    tax_transactions = await repository.list_realized_tax_evidence_transactions(
        **ledger_filters,
    )
    latest_evidence_timestamp = latest_transaction_evidence_timestamp(tax_transactions)

    return RealizedTaxEvidenceRead(
        source_transaction_count=source_transaction_count,
        tax_transactions=tax_transactions,
        latest_evidence_timestamp=latest_evidence_timestamp,
    )
