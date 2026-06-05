from __future__ import annotations

from datetime import datetime
from typing import Any

from ..dtos.core_snapshot_dto import CoreSnapshotFreshnessMetadata


def baseline_freshness_metadata(
    *,
    rows: list[Any],
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
    rows: list[Any],
    has_baseline: bool,
) -> int | None:
    if not has_baseline:
        return None
    return single_resolved_snapshot_epoch(rows)


def latest_snapshot_timestamp(rows: list[Any]) -> datetime | None:
    timestamps: list[datetime] = []
    for row, _instrument, state in rows:
        for candidate in (
            getattr(row, "updated_at", None),
            getattr(row, "created_at", None),
            getattr(state, "updated_at", None),
            getattr(state, "created_at", None),
        ):
            if isinstance(candidate, datetime):
                timestamps.append(candidate)
    return max(timestamps) if timestamps else None


def single_resolved_snapshot_epoch(rows: list[Any]) -> int | None:
    epochs = {
        int(state.epoch)
        for _row, _instrument, state in rows
        if getattr(state, "epoch", None) is not None
    }
    return next(iter(epochs)) if len(epochs) == 1 else None
