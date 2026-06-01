from datetime import datetime
from types import SimpleNamespace

from src.services.query_service.app.services.snapshot_evidence import (
    latest_snapshot_evidence_timestamp,
)


def test_latest_snapshot_evidence_timestamp_prefers_latest_available_update() -> None:
    older = datetime(2026, 3, 27, 9, 0)
    newer = datetime(2026, 3, 27, 10, 0)
    rows = [
        SimpleNamespace(snapshot=SimpleNamespace(created_at=older, updated_at=None)),
        SimpleNamespace(snapshot=SimpleNamespace(created_at=older, updated_at=newer)),
        SimpleNamespace(snapshot=None),
    ]

    assert latest_snapshot_evidence_timestamp(rows) == newer
    assert latest_snapshot_evidence_timestamp([]) is None
