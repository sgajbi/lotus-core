"""Resolve freshness evidence for current and historical snapshot baselines."""

from __future__ import annotations

from datetime import datetime

from ...contracts.core_snapshot import CoreSnapshotFreshnessMetadata
from ...domain.core_snapshot import CoreSnapshotPositionSource


def baseline_freshness_metadata(
    *,
    rows: list[CoreSnapshotPositionSource],
    use_snapshot: bool,
    has_baseline: bool,
) -> CoreSnapshotFreshnessMetadata:
    if not use_snapshot:
        return CoreSnapshotFreshnessMetadata(
            freshness_status="HISTORICAL_FALLBACK",
            baseline_source="position_history",
            snapshot_timestamp=None,
            snapshot_epoch=None,
            fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
        )
    return CoreSnapshotFreshnessMetadata(
        freshness_status="CURRENT_SNAPSHOT",
        baseline_source="position_state",
        snapshot_timestamp=latest_snapshot_timestamp(rows),
        snapshot_epoch=baseline_snapshot_epoch(rows=rows, has_baseline=has_baseline),
        fallback_reason=None,
    )


def baseline_snapshot_epoch(
    *,
    rows: list[CoreSnapshotPositionSource],
    has_baseline: bool,
) -> int | None:
    if not has_baseline:
        return None
    return single_resolved_snapshot_epoch(rows)


def latest_snapshot_timestamp(rows: list[CoreSnapshotPositionSource]) -> datetime | None:
    timestamps: list[datetime] = []
    for row in rows:
        for candidate in (
            row.source_updated_at,
            row.source_created_at,
            row.state_updated_at,
            row.state_created_at,
        ):
            if isinstance(candidate, datetime):
                timestamps.append(candidate)
    return max(timestamps) if timestamps else None


def single_resolved_snapshot_epoch(rows: list[CoreSnapshotPositionSource]) -> int | None:
    epochs = {row.epoch for row in rows}
    return next(iter(epochs)) if len(epochs) == 1 else None
