"""Qualification of persisted cash facts using the shared holdings control policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.reconciliation_quality import (
    COMPLETE,
    PARTIAL,
    UNKNOWN,
    reconciliation_bound_data_quality_status,
)
from portfolio_common.request_fingerprints import request_fingerprint

from .holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScopes,
    dated_holdings_evidence_timestamp,
    holdings_reconciliation_scopes,
    holdings_reconciliation_status,
)


@dataclass(frozen=True)
class CashBalanceEvidence:
    data_quality_status: str
    reconciliation_status: str
    source_evidence_current: bool
    latest_evidence_timestamp: datetime | None
    content_hash: str


def cash_balance_scopes(rows: list[Any]) -> HoldingsReconciliationScopes:
    return holdings_reconciliation_scopes(
        [(row.snapshot, row.instrument, getattr(row, "position_state", None)) for row in rows]
    )


def cash_balance_evidence(
    *,
    rows: list[Any],
    account_records: list[Any],
    resolved_as_of_date: date,
    portfolio_currency: str,
    expected_open_position_count: int,
    controls: list[FinancialReconciliationControl],
) -> CashBalanceEvidence:
    scopes = cash_balance_scopes(rows)
    reconciliation = holdings_reconciliation_status(scopes=scopes, controls=controls)
    cash_rows = {
        str(row.snapshot.security_id).strip(): row
        for row in rows
        if str(getattr(row.instrument, "asset_class", "")).strip().upper() == "CASH"
    }
    timestamps = [
        timestamp
        for row in rows
        if (timestamp := dated_holdings_evidence_timestamp(row.snapshot, row.instrument))
        is not None
    ]
    qualified = bool(account_records) and all(
        _qualified_cash_row(
            cash_rows.get(str(record.security_id).strip()),
            record=record,
            as_of_date=resolved_as_of_date,
            portfolio_currency=portfolio_currency,
        )
        for record in account_records
    )
    open_rows = [row for row in rows if getattr(row.snapshot, "quantity", None) != Decimal("0")]
    qualified = qualified and len(open_rows) >= expected_open_position_count
    qualified = qualified and all(
        row.snapshot.date == resolved_as_of_date
        and row.snapshot.market_value is not None
        and getattr(row.snapshot, "valuation_status", None) == "VALUED_CURRENT"
        and getattr(getattr(row, "position_state", None), "status", None) == "CURRENT"
        for row in rows
    )
    source_quality = COMPLETE if qualified else UNKNOWN
    if qualified and any(
        record.cash_account_id_source == "cash_security_fallback" for record in account_records
    ):
        source_quality = PARTIAL
    quality = reconciliation_bound_data_quality_status(
        source_data_quality_status=source_quality,
        reconciliation_status=reconciliation,
    )
    # A missing completion timestamp cannot certify that controls follow the facts.
    controls_dated = bool(controls) and all(control.updated_at is not None for control in controls)
    current = qualified and quality == COMPLETE and bool(timestamps) and controls_dated
    if quality == COMPLETE and not current:
        quality = UNKNOWN
    return CashBalanceEvidence(
        data_quality_status=quality,
        reconciliation_status=reconciliation,
        source_evidence_current=current,
        latest_evidence_timestamp=max(timestamps, default=None),
        content_hash=request_fingerprint(
            {
                "scopes": scopes.content_hash(),
                "sources": [_source_identity(row) for row in rows],
                "controls": [
                    {
                        "date": control.business_date.isoformat(),
                        "epoch": control.epoch,
                        "status": control.status,
                        "updated_at": _text(control.updated_at),
                    }
                    for control in sorted(
                        controls,
                        key=lambda item: (
                            item.business_date,
                            item.epoch,
                            item.status,
                            _text(item.updated_at) or "",
                        ),
                    )
                ],
                "quality": quality,
                "current": current,
            }
        ),
    )


def _qualified_cash_row(
    row: Any | None,
    *,
    record: Any,
    as_of_date: date,
    portfolio_currency: str,
) -> bool:
    if row is None:
        return False
    snapshot = row.snapshot
    source_currency = getattr(snapshot, "valuation_source_currency", None)
    target_currency = getattr(snapshot, "valuation_reporting_currency", None)
    if (
        snapshot.date != as_of_date
        or getattr(snapshot, "valuation_status", None) != "VALUED_CURRENT"
        or getattr(getattr(row, "position_state", None), "status", None) != "CURRENT"
        or snapshot.market_value is None
        or snapshot.market_value_local is None
        or dated_holdings_evidence_timestamp(snapshot, row.instrument) is None
        or not source_currency
        or not target_currency
        or normalize_currency_code(source_currency)
        != normalize_currency_code(record.account_currency)
        or normalize_currency_code(target_currency) != normalize_currency_code(portfolio_currency)
    ):
        return False
    if source_currency == target_currency:
        return True
    fx_date = getattr(snapshot, "valuation_fx_rate_date", None)
    fx_rate = getattr(snapshot, "valuation_fx_rate", None)
    return (
        fx_date == as_of_date
        and isinstance(fx_rate, Decimal)
        and fx_rate.is_finite()
        and fx_rate > 0
    )


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _source_identity(row: Any) -> dict[str, Any]:
    snapshot_fields = (
        "id",
        "security_id",
        "date",
        "epoch",
        "quantity",
        "market_value",
        "market_value_local",
        "valuation_status",
        "valuation_source_currency",
        "valuation_reporting_currency",
        "valuation_fx_rate_date",
        "valuation_fx_rate",
    )
    return {
        **{field: _text(getattr(row.snapshot, field, None)) for field in snapshot_fields},
        "state_epoch": getattr(getattr(row, "position_state", None), "epoch", None),
        "state_status": getattr(getattr(row, "position_state", None), "status", None),
        "dated_evidence": _text(dated_holdings_evidence_timestamp(row.snapshot, row.instrument)),
    }
