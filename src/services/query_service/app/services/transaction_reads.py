from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..application.transaction_query import (
    TransactionLedgerFilters,
    TransactionLedgerInputEvidence,
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
    evidence_as_of_date: date | None
    latest_evidence_timestamp: datetime | None
    missing_instrument_security_ids: list[str]
    input_evidence: TransactionLedgerInputEvidence


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
    reporting_currency: str | None,
) -> TransactionLedgerPage:
    query_spec = transaction_ledger_query_spec(
        filters=ledger_filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    input_evidence = await repository.get_transaction_ledger_input_evidence(
        filters=query_spec.filters,
        reporting_currency=reporting_currency,
        as_of_date=query_spec.filters.as_of_date,
    )
    total_count = input_evidence.transaction_count
    if total_count == 0:
        return TransactionLedgerPage(
            total_count=0,
            rows=[],
            evidence_as_of_date=query_spec.filters.as_of_date,
            latest_evidence_timestamp=input_evidence.latest_evidence_timestamp,
            missing_instrument_security_ids=[],
            input_evidence=input_evidence,
        )

    rows = await repository.get_transactions(
        skip=skip,
        limit=limit,
        query_spec=query_spec,
    )

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
        evidence_as_of_date=query_spec.filters.as_of_date,
        latest_evidence_timestamp=input_evidence.latest_evidence_timestamp,
        missing_instrument_security_ids=missing_instrument_security_ids,
        input_evidence=input_evidence,
    )


async def read_exact_transaction_ledger_record(
    *,
    repository: Any,
    ledger_filters: TransactionLedgerFilters,
    reporting_currency: str | None,
) -> TransactionLedgerPage:
    """Read one exact record before resolving its projected FX/proof boundary."""

    query_spec = transaction_ledger_query_spec(
        filters=ledger_filters,
        sort_by=None,
        sort_order="desc",
    )
    rows = await repository.get_transactions(
        skip=0,
        limit=2,
        query_spec=query_spec,
    )
    evidence_as_of_date = ledger_filters.as_of_date
    if evidence_as_of_date is None and len(rows) == 1:
        evidence_as_of_date = rows[0].transaction_date.date()

    input_evidence = await repository.get_transaction_ledger_input_evidence(
        filters=query_spec.filters,
        reporting_currency=reporting_currency,
        as_of_date=evidence_as_of_date,
    )
    if not rows:
        return TransactionLedgerPage(
            total_count=input_evidence.transaction_count,
            rows=[],
            evidence_as_of_date=evidence_as_of_date,
            latest_evidence_timestamp=input_evidence.latest_evidence_timestamp,
            missing_instrument_security_ids=[],
            input_evidence=input_evidence,
        )

    known_instrument_security_ids = await repository.list_known_instrument_security_ids(
        transaction_security_ids(rows)
    )
    missing_instrument_security_ids = missing_transaction_instrument_security_ids(
        transactions=rows,
        known_instrument_security_ids=known_instrument_security_ids,
    )
    return TransactionLedgerPage(
        total_count=input_evidence.transaction_count,
        rows=rows,
        evidence_as_of_date=evidence_as_of_date,
        latest_evidence_timestamp=input_evidence.latest_evidence_timestamp,
        missing_instrument_security_ids=missing_instrument_security_ids,
        input_evidence=input_evidence,
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
