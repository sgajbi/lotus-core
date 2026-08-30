from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


def _export_model(job_id: str = "aexp_1") -> SimpleNamespace:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    return SimpleNamespace(
        job_id=job_id,
        tenant_id="tenant-a",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status="accepted",
        request_fingerprint="fp1",
        request_payload={"x": 1},
        result_payload=None,
        result_row_count=None,
        result_format="json",
        compression="none",
        error_message=None,
        created_at=now,
        started_at=None,
        completed_at=None,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_analytics_export_repository_create_get_and_markers() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = AnalyticsExportRepository(db)

    await repo.create_job(
        job_id="aexp_1",
        tenant_id="tenant-a",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        request_fingerprint="fp1",
        request_payload={"x": 1},
        result_format="json",
        compression="none",
    )
    assert db.add.call_count == 1
    assert db.flush.await_count == 1

    model = _export_model()
    db.execute.return_value = _FakeExecuteResult([model])
    record = await repo.get_job(tenant_id="tenant-a", job_id="aexp_1")
    assert record is not None
    job_stmt = db.execute.await_args.args[0]
    job_sql = str(job_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "analytics_export_jobs.tenant_id = 'tenant-a'" in job_sql
    assert "analytics_export_jobs.job_id = 'aexp_1'" in job_sql

    running = await repo.mark_running(record, tenant_id="tenant-a")
    assert running.status == "running"
    completed = await repo.mark_completed(
        running,
        tenant_id="tenant-a",
        result_payload={"a": 1},
        result_row_count=2,
    )
    assert completed.status == "completed"
    failed = await repo.mark_failed(completed, tenant_id="tenant-a", error_message="failed")
    assert failed.status == "failed"

    db.execute.return_value = _FakeExecuteResult([_export_model("aexp_1")])
    got = await repo.get_job(tenant_id="tenant-a", job_id="aexp_1")
    assert got is not None

    db.execute.return_value = _FakeExecuteResult([_export_model("aexp_2")])
    got_fp = await repo.get_latest_by_fingerprint(
        tenant_id="tenant-a", request_fingerprint="fp", dataset_type="x"
    )
    assert got_fp is not None

    fingerprint_stmt = db.execute.await_args.args[0]
    fingerprint_sql = str(fingerprint_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "analytics_export_jobs.tenant_id = 'tenant-a'" in fingerprint_sql
    assert "analytics_export_jobs.request_fingerprint = 'fp'" in fingerprint_sql
    assert "analytics_export_jobs.dataset_type = 'x'" in fingerprint_sql
    assert "ORDER BY analytics_export_jobs.id DESC" in fingerprint_sql
