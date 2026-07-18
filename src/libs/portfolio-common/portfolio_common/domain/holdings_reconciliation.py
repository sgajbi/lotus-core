"""Framework-independent reconciliation policy for holdings-derived source products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

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
    """One exact business-date/epoch source scope represented in holdings state."""

    business_date: date
    epoch: int
    latest_evidence_timestamp: datetime | None
    source_row_count: int


@dataclass(frozen=True, slots=True)
class HoldingsReconciliationScopes:
    """Exact control requirements extracted by an owning source adapter."""

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


def _timestamp_precedes(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return _as_utc(left) < _as_utc(right)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
