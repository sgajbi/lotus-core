from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from .transaction_metadata import (
    latest_transaction_evidence_timestamp,
    missing_transaction_instrument_security_ids,
    transaction_security_ids,
)


@dataclass(frozen=True)
class TransactionLedgerPage:
    total_count: int
    rows: list[Any]
    latest_evidence_timestamp: datetime | None
    missing_instrument_security_ids: list[str]


@dataclass(frozen=True)
class RealizedTaxEvidenceRead:
    source_transaction_count: int
    tax_transactions: list[Any]
    latest_evidence_timestamp: datetime | None


async def read_transaction_ledger_page(
    *,
    repository: Any,
    ledger_filters: TransactionLedgerFilters,
    skip: int,
    limit: int,
    sort_by: str | None,
    sort_order: str | None,
) -> TransactionLedgerPage:
    query_spec = transaction_ledger_query_spec(
        filters=ledger_filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_count = await repository.get_transactions_count(filters=query_spec.filters)
    if total_count == 0:
        return TransactionLedgerPage(
            total_count=0,
            rows=[],
            latest_evidence_timestamp=None,
            missing_instrument_security_ids=[],
        )

    rows = await repository.get_transactions(
        skip=skip,
        limit=limit,
        query_spec=query_spec,
    )

    if skip > 0 or limit < total_count or len(rows) != total_count:
        latest_evidence_timestamp = await repository.get_latest_evidence_timestamp(
            filters=query_spec.filters
        )
    else:
        latest_evidence_timestamp = latest_transaction_evidence_timestamp(rows)

    known_instrument_security_ids = await repository.list_known_instrument_security_ids(
        transaction_security_ids(rows)
    )
    missing_instrument_security_ids = missing_transaction_instrument_security_ids(
        transactions=rows,
        known_instrument_security_ids=known_instrument_security_ids,
    )

    return TransactionLedgerPage(
        total_count=total_count,
        rows=rows,
        latest_evidence_timestamp=latest_evidence_timestamp,
        missing_instrument_security_ids=missing_instrument_security_ids,
    )


async def read_realized_tax_evidence(
    *,
    repository: Any,
    ledger_filters: TransactionLedgerFilters,
) -> RealizedTaxEvidenceRead:
    source_transaction_count = await repository.get_transactions_count(filters=ledger_filters)
    tax_transactions = await repository.list_realized_tax_evidence_transactions(
        filters=ledger_filters,
    )
    latest_evidence_timestamp = latest_transaction_evidence_timestamp(tax_transactions)

    return RealizedTaxEvidenceRead(
        source_transaction_count=source_transaction_count,
        tax_transactions=tax_transactions,
        latest_evidence_timestamp=latest_evidence_timestamp,
    )
