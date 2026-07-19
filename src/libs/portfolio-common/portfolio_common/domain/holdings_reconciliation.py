"""Framework-independent reconciliation policy for holdings-derived source products."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TypeGuard

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
    """One collective portfolio-day target epoch represented in holdings state."""

    business_date: date
    epoch: int
    latest_evidence_timestamp: datetime | None
    source_row_count: int


@dataclass(frozen=True, slots=True)
class HoldingsReconciliationScopes:
    """Collective control requirements extracted by an owning source adapter."""

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
class HoldingsReconciliationSource:
    """Normalized source fact used to derive a collective portfolio-day scope."""

    business_date: date | None
    row_epoch: int | None
    state_epoch: int | None
    latest_evidence_timestamp: datetime | None


def collective_holdings_reconciliation_scopes(
    sources: list[HoldingsReconciliationSource],
) -> HoldingsReconciliationScopes:
    """Coalesce valid rows by day at the maximum portfolio-state epoch.

    A security row's epoch records its last mutation, not a requirement for a
    separate portfolio-day control. Rows whose persisted and state epochs do not
    agree remain unscoped so reconciliation quality continues to fail closed.
    """

    grouped: dict[date, tuple[int, datetime | None, int]] = {}
    unscoped_count = 0
    for source in sources:
        if (
            source.business_date is None
            or not _valid_epoch(source.row_epoch)
            or not _valid_epoch(source.state_epoch)
            or source.row_epoch != source.state_epoch
        ):
            unscoped_count += 1
            continue
        prior_epoch, prior_timestamp, prior_count = grouped.get(
            source.business_date,
            (source.row_epoch, None, 0),
        )
        grouped[source.business_date] = (
            max(prior_epoch, source.row_epoch),
            _latest_timestamp(prior_timestamp, source.latest_evidence_timestamp),
            prior_count + 1,
        )

    return HoldingsReconciliationScopes(
        items=tuple(
            HoldingsReconciliationScope(
                business_date=business_date,
                epoch=epoch,
                latest_evidence_timestamp=latest_timestamp,
                source_row_count=row_count,
            )
            for business_date, (epoch, latest_timestamp, row_count) in sorted(grouped.items())
        ),
        unscoped_source_row_count=unscoped_count,
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

    controls_by_scope: dict[tuple[date, int], list[FinancialReconciliationControl]] = {}
    for control in controls:
        controls_by_scope.setdefault((control.business_date, control.epoch), []).append(control)
    statuses = [UNKNOWN] * scopes.unscoped_source_row_count
    for scope in scopes.items:
        scope_controls = controls_by_scope.get((scope.business_date, scope.epoch), [])
        statuses.append(
            _aggregate_reconciliation_statuses(
                [
                    _scope_reconciliation_status(scope=scope, control=control)
                    for control in scope_controls
                ]
            )
        )
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


def _valid_epoch(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _latest_timestamp(*values: datetime | None) -> datetime | None:
    return max((_as_utc(value) for value in values if value is not None), default=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
