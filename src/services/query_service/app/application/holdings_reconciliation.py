"""Exact-scope reconciliation policy for HoldingsAsOf source rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScope,
    HoldingsReconciliationScopes,
    HoldingsReconciliationSource,
    collective_holdings_reconciliation_scopes,
    holdings_reconciliation_status,
)

__all__ = [
    "FinancialReconciliationControl",
    "HoldingsReconciliationScope",
    "HoldingsReconciliationScopes",
    "holdings_reconciliation_scopes",
    "holdings_reconciliation_status",
    "dated_holdings_evidence_timestamp",
    "HoldingsReconciliationEvidence",
    "holdings_reconciliation_evidence_scopes",
    "holdings_reconciliation_evidence_hash",
    "latest_reconciliation_evidence_timestamp",
    "is_qualified_closed_cohort",
]


@dataclass(frozen=True, slots=True)
class HoldingsReconciliationEvidence:
    """Persisted facts for one dated security, including scope-only closed rows."""

    history: Any
    snapshot: Any
    instrument: Any
    state: Any
    portfolio_currency: str | None = None
    portfolio_evidence_timestamp: datetime | None = None


def holdings_reconciliation_evidence_hash(
    rows: list[HoldingsReconciliationEvidence], scopes: HoldingsReconciliationScopes
) -> str:
    """Bind scope-only economics, including invalid revisions, without completion clocks."""
    fields = {
        "history": (
            "security_id",
            "position_date",
            "epoch",
            "quantity",
            "cost_basis",
            "cost_basis_local",
            "created_at",
            "updated_at",
        ),
        "snapshot": (
            "date",
            "epoch",
            "quantity",
            "cost_basis",
            "cost_basis_local",
            "market_value",
            "market_value_local",
            "valuation_status",
            "valuation_source_currency",
            "valuation_reporting_currency",
            "valuation_fx_rate",
            "valuation_fx_rate_date",
            "created_at",
            "updated_at",
        ),
        "instrument": ("security_id", "currency", "created_at", "updated_at"),
        "state": ("security_id", "epoch", "status"),
    }
    material = [
        {
            "portfolio_currency": row.portfolio_currency,
            "portfolio_evidence_timestamp": row.portfolio_evidence_timestamp,
            **{
                name: {field: getattr(getattr(row, name), field, None) for field in keys}
                for name, keys in fields.items()
            },
        }
        for row in rows
    ]
    return canonical_content_hash(
        {
            "scopes": scopes.content_hash(),
            "sources": sorted(material, key=canonical_content_hash),
        }
    )


def latest_reconciliation_evidence_timestamp(
    rows: list[HoldingsReconciliationEvidence],
) -> datetime | None:
    return _latest_timestamp(*(_cohort_evidence_timestamp(row) for row in rows))


def _cohort_evidence_timestamp(row: HoldingsReconciliationEvidence) -> datetime | None:
    return _latest_timestamp(
        dated_holdings_evidence_timestamp(row.history, row.instrument),
        dated_holdings_evidence_timestamp(row.snapshot, row.instrument),
        row.portfolio_evidence_timestamp,
    )


def is_qualified_closed_cohort(
    rows: list[HoldingsReconciliationEvidence], scopes: HoldingsReconciliationScopes
) -> bool:
    """Observed valued zero is distinct from an empty or incomplete source cohort."""
    return (
        bool(rows)
        and not scopes.unscoped_source_row_count
        and all(row.history is not None and row.history.quantity == 0 for row in rows)
    )


def holdings_reconciliation_evidence_scopes(
    rows: list[HoldingsReconciliationEvidence],
) -> HoldingsReconciliationScopes:
    """Keep invalid members unscoped; do not silently fall back to older authority."""
    sources = []
    for row in rows:
        history, snapshot, instrument, state = (
            row.history,
            row.snapshot,
            row.instrument,
            row.state,
        )
        history_day = _source_business_date(history)
        valid = instrument is not None and state is not None and history_day is not None
        if snapshot is not None:
            valid = valid and (
                snapshot.epoch == history.epoch
                and snapshot.quantity == history.quantity
                and snapshot.date >= history_day
            )
        if getattr(history, "quantity", None) == 0:
            valid = valid and _qualified_zero_evidence(row)
        dated_source = snapshot if snapshot is not None else history
        sources.append(
            HoldingsReconciliationSource(
                business_date=_source_business_date(dated_source),
                row_epoch=history.epoch if valid else None,
                state_epoch=getattr(state, "epoch", None),
                latest_evidence_timestamp=_cohort_evidence_timestamp(row),
            )
        )
    return collective_holdings_reconciliation_scopes(sources)


def _qualified_zero_evidence(row: HoldingsReconciliationEvidence) -> bool:
    snapshot = row.snapshot
    if snapshot is None or row.state.status != "CURRENT":
        return False
    if (
        snapshot.valuation_status != "VALUED_CURRENT"
        or snapshot.market_value != 0
        or snapshot.market_value_local != 0
        or not snapshot.valuation_source_currency
        or not snapshot.valuation_reporting_currency
        or not row.portfolio_currency
    ):
        return False
    try:
        currencies_match = normalize_currency_code(
            snapshot.valuation_source_currency
        ) == normalize_currency_code(row.instrument.currency) and normalize_currency_code(
            snapshot.valuation_reporting_currency
        ) == normalize_currency_code(row.portfolio_currency)
    except ValueError:
        return False
    if not currencies_match:
        return False
    if snapshot.valuation_source_currency == snapshot.valuation_reporting_currency:
        return True
    rate = getattr(snapshot, "valuation_fx_rate", None)
    return (
        getattr(snapshot, "valuation_fx_rate_date", None) == snapshot.date
        and isinstance(rate, Decimal)
        and rate.is_finite()
        and rate > 0
    )


def holdings_reconciliation_scopes(
    source_rows: list[tuple[Any, Any, Any]],
) -> HoldingsReconciliationScopes:
    """Extract collective portfolio-day scopes from selected source rows."""

    return collective_holdings_reconciliation_scopes(
        [
            HoldingsReconciliationSource(
                business_date=_source_business_date(position_row),
                row_epoch=getattr(position_row, "epoch", None),
                state_epoch=getattr(position_state, "epoch", None),
                latest_evidence_timestamp=dated_holdings_evidence_timestamp(
                    position_row, instrument
                ),
            )
            for position_row, instrument, position_state in source_rows
        ]
    )


def dated_holdings_evidence_timestamp(position_row: Any, instrument: Any) -> datetime | None:
    """Project selected dated facts/reference evidence, not shared replay bookkeeping.

    State epoch remains part of exact scope admission and state status remains part of
    holdings qualification. Its completion timestamps do not date historical economics.
    """
    return _latest_timestamp(
        *(
            getattr(source, field_name, None)
            for source in (position_row, instrument)
            for field_name in ("created_at", "updated_at")
        )
    )


def _source_business_date(position_row: Any) -> date | None:
    for field_name in ("date", "position_date"):
        candidate = getattr(position_row, field_name, None)
        if isinstance(candidate, date):
            return candidate
    return None


def _latest_timestamp(*values: object) -> datetime | None:
    timestamps = [_as_utc(value) for value in values if isinstance(value, datetime)]
    return max(timestamps, default=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
