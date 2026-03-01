from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.analytics_export_repository import (
    AnalyticsExportRepository,
)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


@pytest.mark.asyncio
async def test_analytics_export_repository_create_get_and_markers() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = AnalyticsExportRepository(db)

    await repo.create_job(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        request_fingerprint="fp1",
        request_payload={"x": 1},
        result_format="json",
        compression="none",
    )
    assert db.add.call_count == 1
    assert db.flush.await_count == 1

    row = SimpleNamespace(
        status="accepted",
        started_at=None,
        completed_at=None,
        result_payload=None,
        result_row_count=None,
        error_message=None,
    )
    await repo.mark_running(row)
    assert row.status == "running"
    await repo.mark_completed(row, result_payload={"a": 1}, result_row_count=2)
    assert row.status == "completed"
    await repo.mark_failed(row, error_message="failed")
    assert row.status == "failed"

    db.execute.return_value = _FakeExecuteResult([SimpleNamespace(job_id="aexp_1")])
    got = await repo.get_job("aexp_1")
    assert got is not None

    db.execute.return_value = _FakeExecuteResult([SimpleNamespace(job_id="aexp_2")])
    got_fp = await repo.get_latest_by_fingerprint(request_fingerprint="fp", dataset_type="x")
    assert got_fp is not None
