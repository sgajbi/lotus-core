"""Extract exact reconciliation scopes from Core snapshot source records."""

from __future__ import annotations

from datetime import UTC, date, datetime

from portfolio_common.domain.holdings_reconciliation import (
    HoldingsReconciliationScope,
    HoldingsReconciliationScopes,
)

from ...domain.core_snapshot import CoreSnapshotPositionSource


def core_snapshot_reconciliation_scopes(
    rows: list[CoreSnapshotPositionSource],
) -> HoldingsReconciliationScopes:
    """Coalesce selected baseline rows by exact business date and epoch."""

    grouped: dict[tuple[date, int], tuple[datetime | None, int]] = {}
    unscoped_count = 0
    for row in rows:
        if row.business_date is None or row.epoch < 0:
            unscoped_count += 1
            continue
        key = (row.business_date, row.epoch)
        prior_timestamp, prior_count = grouped.get(key, (None, 0))
        grouped[key] = (
            _latest_timestamp(
                prior_timestamp,
                row.source_created_at,
                row.source_updated_at,
                row.state_created_at,
                row.state_updated_at,
            ),
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
            for (business_date, epoch), (latest_timestamp, row_count) in sorted(grouped.items())
        ),
        unscoped_source_row_count=unscoped_count,
    )


def _latest_timestamp(*values: datetime | None) -> datetime | None:
    return max((_as_utc(value) for value in values if value is not None), default=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
