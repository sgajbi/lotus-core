from __future__ import annotations

from datetime import datetime
from typing import Any


def latest_snapshot_evidence_timestamp(rows: list[Any]) -> datetime | None:
    timestamps: list[datetime] = []
    for row in rows:
        snapshot = getattr(row, "snapshot", None)
        for candidate in (
            getattr(snapshot, "updated_at", None),
            getattr(snapshot, "created_at", None),
        ):
            if isinstance(candidate, datetime):
                timestamps.append(candidate)
    return max(timestamps) if timestamps else None
