"""Exact-scope reconciliation policy for HoldingsAsOf source rows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

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
]


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
                latest_evidence_timestamp=_latest_timestamp(
                    *(
                        getattr(source, field_name, None)
                        for source in (position_row, instrument, position_state)
                        for field_name in ("created_at", "updated_at")
                    )
                ),
            )
            for position_row, instrument, position_state in source_rows
        ]
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
