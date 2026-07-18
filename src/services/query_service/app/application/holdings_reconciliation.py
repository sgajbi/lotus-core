"""Exact-scope reconciliation policy for HoldingsAsOf source rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    UNRECONCILED,
)


@dataclass(frozen=True, slots=True)
class HoldingsReconciliationScope:
    """One exact business-date/epoch source scope represented in HoldingsAsOf."""

    business_date: date
    epoch: int
    latest_evidence_timestamp: datetime | None
    source_row_count: int


@dataclass(frozen=True, slots=True)
class HoldingsReconciliationScopes:
    """Reconciliation requirements extracted before source rows become API DTOs."""

    items: tuple[HoldingsReconciliationScope, ...]
    unscoped_source_row_count: int = 0

    def content_hash(self) -> str:
        return canonical_content_hash(
            {
                "scopes": [
                    {
                        "business_date": scope.business_date,
                        "epoch": scope.epoch,
                        "latest_evidence_timestamp": scope.latest_evidence_timestamp,
                        "source_row_count": scope.source_row_count,
                    }
                    for scope in self.items
                ],
                "unscoped_source_row_count": self.unscoped_source_row_count,
            }
        )


@dataclass(frozen=True, slots=True)
class FinancialReconciliationControl:
    """Durable aggregate control outcome for one portfolio-day/epoch."""

    business_date: date
    epoch: int
    status: str
    updated_at: datetime | None


def holdings_reconciliation_scopes(
    source_rows: list[tuple[Any, Any, Any]],
) -> HoldingsReconciliationScopes:
    """Extract exact scopes and evidence timestamps from selected source rows."""

    grouped: dict[tuple[date, int], tuple[datetime | None, int]] = {}
    unscoped_count = 0
    for position_row, instrument, position_state in source_rows:
        business_date = _source_business_date(position_row)
        row_epoch = getattr(position_row, "epoch", None)
        state_epoch = getattr(position_state, "epoch", None)
        if (
            business_date is None
            or not isinstance(row_epoch, int)
            or not isinstance(state_epoch, int)
            or row_epoch != state_epoch
        ):
            unscoped_count += 1
            continue
        key = (business_date, row_epoch)
        prior_timestamp, prior_count = grouped.get(key, (None, 0))
        grouped[key] = (
            _latest_timestamp(
                prior_timestamp,
                *(
                    getattr(source, field_name, None)
                    for source in (position_row, instrument, position_state)
                    for field_name in ("created_at", "updated_at")
                ),
            ),
            prior_count + 1,
        )

    return HoldingsReconciliationScopes(
        items=tuple(
            HoldingsReconciliationScope(
                business_date=business_date,
                epoch=epoch,
                latest_evidence_timestamp=timestamp,
                source_row_count=count,
            )
            for (business_date, epoch), (timestamp, count) in sorted(grouped.items())
        ),
        unscoped_source_row_count=unscoped_count,
    )


def holdings_reconciliation_status(
    *,
    scopes: HoldingsReconciliationScopes,
    controls: list[FinancialReconciliationControl],
) -> str:
    """Aggregate exact control evidence without treating missing proof as success."""

    if not scopes.items and scopes.unscoped_source_row_count == 0:
        return UNRECONCILED

    control_by_scope = {(control.business_date, control.epoch): control for control in controls}
    statuses = [UNKNOWN] * scopes.unscoped_source_row_count
    for scope in scopes.items:
        control = control_by_scope.get((scope.business_date, scope.epoch))
        statuses.append(_scope_reconciliation_status(scope=scope, control=control))
    return _aggregate_reconciliation_statuses(statuses)


def _scope_reconciliation_status(
    *,
    scope: HoldingsReconciliationScope,
    control: FinancialReconciliationControl | None,
) -> str:
    if control is None:
        return UNRECONCILED
    normalized_status = control.status.strip().upper()
    if normalized_status in {"FAILED", "REQUIRES_REPLAY", "BLOCKED"}:
        return BLOCKED
    if normalized_status in {"PENDING", "RUNNING", "PROCESSING", "QUEUED"}:
        return PARTIAL
    if normalized_status != "COMPLETED":
        return UNKNOWN
    if _timestamp_precedes(control.updated_at, scope.latest_evidence_timestamp):
        return STALE
    return COMPLETE


def _aggregate_reconciliation_statuses(statuses: list[str]) -> str:
    if not statuses:
        return UNRECONCILED
    for status in (BLOCKED, STALE, UNRECONCILED, UNKNOWN, PARTIAL):
        if status in statuses:
            return status
    return COMPLETE


def _source_business_date(position_row: Any) -> date | None:
    for field_name in ("date", "position_date"):
        candidate = getattr(position_row, field_name, None)
        if isinstance(candidate, date):
            return candidate
    return None


def _latest_timestamp(*values: object) -> datetime | None:
    timestamps = [_as_utc(value) for value in values if isinstance(value, datetime)]
    return max(timestamps, default=None)


def _timestamp_precedes(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return _as_utc(left) < _as_utc(right)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
