from __future__ import annotations

from typing import cast

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from ..dtos.core_snapshot_dto import CoreSnapshotFreshnessMetadata


def snapshot_data_quality_status(
    *,
    freshness: CoreSnapshotFreshnessMetadata,
    baseline_count: int,
) -> str:
    if baseline_count <= 0:
        return cast(str, UNKNOWN)
    freshness_status = _normalize_freshness_status(freshness.freshness_status)
    if freshness_status == "HISTORICAL_FALLBACK":
        return cast(str, PARTIAL)
    if _is_complete_current_snapshot(
        freshness=freshness,
        freshness_status=freshness_status,
    ):
        return cast(str, COMPLETE)
    return cast(str, PARTIAL)


def _normalize_freshness_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized_status = status.strip().upper()
    return normalized_status or None


def _is_complete_current_snapshot(
    *,
    freshness: CoreSnapshotFreshnessMetadata,
    freshness_status: str | None,
) -> bool:
    return (
        freshness_status == "CURRENT_SNAPSHOT"
        and freshness.snapshot_timestamp is not None
        and freshness.snapshot_epoch is not None
    )
