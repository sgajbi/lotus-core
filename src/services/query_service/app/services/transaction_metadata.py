from datetime import date, datetime
from typing import cast

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from ..application.transaction_query import (
    TransactionLedgerFilters,
)
from ..application.transaction_query import (
    transaction_ledger_filters as build_transaction_ledger_filters,
)
from ..repositories.identifier_normalization import normalize_security_id

TRANSACTION_LEDGER_READY = "TRANSACTION_LEDGER_READY"
TRANSACTION_LEDGER_EMPTY = "TRANSACTION_LEDGER_EMPTY"
TRANSACTION_LEDGER_PAGE_PARTIAL = "TRANSACTION_LEDGER_PAGE_PARTIAL"
TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING = "TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING"


def ledger_data_quality_status(
    *,
    total_count: int,
    returned_count: int,
    skip: int,
    missing_instrument_security_ids: list[str] | None = None,
) -> str:
    if total_count <= 0:
        return cast(str, UNKNOWN)
    if missing_instrument_security_ids:
        return cast(str, PARTIAL)
    if skip > 0 or returned_count < total_count:
        return cast(str, PARTIAL)
    return cast(str, COMPLETE)


def ledger_reason_codes(
    *,
    total_count: int,
    returned_count: int,
    skip: int,
    missing_instrument_security_ids: list[str] | None = None,
) -> list[str]:
    if total_count <= 0:
        return [TRANSACTION_LEDGER_EMPTY]
    reason_codes: list[str] = []
    if missing_instrument_security_ids:
        reason_codes.append(TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING)
    if skip > 0 or returned_count < total_count:
        reason_codes.append(TRANSACTION_LEDGER_PAGE_PARTIAL)
    return reason_codes or [TRANSACTION_LEDGER_READY]


def latest_transaction_evidence_timestamp(transactions: list[object]) -> datetime | None:
    return max(
        (
            updated_at
            for transaction in transactions
            if (updated_at := getattr(transaction, "updated_at", None)) is not None
        ),
        default=None,
    )


def transaction_security_ids(transactions: list[object]) -> list[str]:
    return list(
        dict.fromkeys(
            normalized
            for transaction in transactions
            if (
                normalized := normalize_security_id(
                    cast(str | None, getattr(transaction, "security_id", None))
                )
            )
        )
    )


def missing_transaction_instrument_security_ids(
    *,
    transactions: list[object],
    known_instrument_security_ids: set[str],
) -> list[str]:
    normalized_known_security_ids = {
        normalized
        for security_id in known_instrument_security_ids
        if (normalized := normalize_security_id(security_id))
    }
    return [
        security_id
        for security_id in transaction_security_ids(transactions)
        if security_id not in normalized_known_security_ids
    ]


def transaction_ledger_filters(
    *,
    portfolio_id: str,
    instrument_id: str | None,
    security_id: str | None,
    transaction_type: str | None,
    component_type: str | None,
    linked_transaction_group_id: str | None,
    fx_contract_id: str | None,
    swap_event_id: str | None,
    near_leg_group_id: str | None,
    far_leg_group_id: str | None,
    start_date: date | None,
    end_date: date | None,
    as_of_date: date | None,
) -> TransactionLedgerFilters:
    return build_transaction_ledger_filters(
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        security_id=security_id,
        transaction_type=transaction_type,
        component_type=component_type,
        linked_transaction_group_id=linked_transaction_group_id,
        fx_contract_id=fx_contract_id,
        swap_event_id=swap_event_id,
        near_leg_group_id=near_leg_group_id,
        far_leg_group_id=far_leg_group_id,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
    )


def realized_tax_summary_filters(
    *,
    portfolio_id: str,
    start_date: date | None,
    end_date: date | None,
    as_of_date: date,
) -> TransactionLedgerFilters:
    return TransactionLedgerFilters(
        portfolio_id=portfolio_id,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
    )
