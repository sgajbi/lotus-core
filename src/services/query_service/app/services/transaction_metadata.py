from datetime import date, datetime
from typing import Any, cast

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
) -> dict[str, Any]:
    return {
        "portfolio_id": portfolio_id,
        "instrument_id": instrument_id,
        "security_id": security_id,
        "transaction_type": transaction_type,
        "component_type": component_type,
        "linked_transaction_group_id": linked_transaction_group_id,
        "fx_contract_id": fx_contract_id,
        "swap_event_id": swap_event_id,
        "near_leg_group_id": near_leg_group_id,
        "far_leg_group_id": far_leg_group_id,
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": as_of_date,
    }


def realized_tax_summary_filters(
    *,
    portfolio_id: str,
    start_date: date | None,
    end_date: date | None,
    as_of_date: date,
) -> dict[str, Any]:
    return {
        "portfolio_id": portfolio_id,
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": as_of_date,
    }
