from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .transaction_sorting import normalize_transaction_sort


class TransactionRecordUnavailableError(RuntimeError):
    """The exact transaction source could not be read authoritatively."""


@dataclass(frozen=True, slots=True)
class TransactionLedgerFilters:
    portfolio_id: str
    transaction_id: str | None = None
    instrument_id: str | None = None
    security_id: str | None = None
    transaction_type: str | None = None
    component_type: str | None = None
    linked_transaction_group_id: str | None = None
    fx_contract_id: str | None = None
    swap_event_id: str | None = None
    near_leg_group_id: str | None = None
    far_leg_group_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    as_of_date: date | None = None


@dataclass(frozen=True, slots=True)
class TransactionLedgerInputEvidence:
    """Page-independent evidence for every material ledger input family."""

    transaction_count: int
    latest_evidence_timestamp: datetime | None
    transaction_digest: str | None
    transaction_cost_digest: str | None
    selected_cashflow_digest: str | None
    selected_fx_rate_digest: str | None


@dataclass(frozen=True, slots=True)
class TransactionSortSpec:
    field: str
    order: str

    @classmethod
    def from_request(
        cls,
        *,
        sort_by: str | None,
        sort_order: str | None,
    ) -> TransactionSortSpec:
        field, order = normalize_transaction_sort(sort_by=sort_by, sort_order=sort_order)
        return cls(field=field, order=order)


@dataclass(frozen=True, slots=True)
class TransactionLedgerQuerySpec:
    filters: TransactionLedgerFilters
    sort: TransactionSortSpec


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
    transaction_id: str | None = None,
) -> TransactionLedgerFilters:
    return TransactionLedgerFilters(
        portfolio_id=portfolio_id,
        transaction_id=transaction_id,
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


def transaction_ledger_query_spec(
    *,
    filters: TransactionLedgerFilters,
    sort_by: str | None,
    sort_order: str | None,
) -> TransactionLedgerQuerySpec:
    return TransactionLedgerQuerySpec(
        filters=filters,
        sort=TransactionSortSpec.from_request(sort_by=sort_by, sort_order=sort_order),
    )
