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


class _ExpiredTimestampModel(SimpleNamespace):
    """Represent PostgreSQL's expired server-generated value after an update flush."""

    def __getattribute__(self, name):
        if name == "updated_at" and self.timestamp_expired:
            raise RuntimeError("Implicit async IO during synchronous record projection")
        return super().__getattribute__(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["running", "completed", "failed"])
async def test_export_transition_refreshes_server_timestamp_before_projection(transition):
    db = AsyncMock(spec=AsyncSession)
    model = _ExpiredTimestampModel(**vars(_export_model()), timestamp_expired=False)
    db.execute.return_value = _FakeExecuteResult([model])
    repo = AnalyticsExportRepository(db)
    record = await repo.get_job(model.job_id)
    refreshed_time = datetime(2026, 7, 12, tzinfo=UTC)

    async def expire_timestamp():
        model.timestamp_expired = True

    async def refresh_timestamp(row, *, attribute_names):
        assert row is model and attribute_names == ["updated_at"]
        row.updated_at = refreshed_time
        row.timestamp_expired = False

    db.flush.side_effect = expire_timestamp
    db.refresh.side_effect = refresh_timestamp
    if transition == "running":
        result = await repo.mark_running(record)
    elif transition == "completed":
        result = await repo.mark_completed(
            record, result_payload={"evidence": "retained"}, result_row_count=1
        )
    else:
        result = await repo.mark_failed(record, error_message="Conflicting source cuts")
    assert result.status == transition
    assert result.updated_at == refreshed_time
    db.refresh.assert_awaited_once_with(model, attribute_names=["updated_at"])


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

    model = _export_model()
    db.execute.return_value = _FakeExecuteResult([model])
    record = await repo.get_job("aexp_1")
    assert record is not None

    running = await repo.mark_running(record)
    assert running.status == "running"
    completed = await repo.mark_completed(running, result_payload={"a": 1}, result_row_count=2)
    assert completed.status == "completed"
    failed = await repo.mark_failed(completed, error_message="failed")
    assert failed.status == "failed"

    db.execute.return_value = _FakeExecuteResult([_export_model("aexp_1")])
    got = await repo.get_job("aexp_1")
    assert got is not None

    db.execute.return_value = _FakeExecuteResult([_export_model("aexp_2")])
    got_fp = await repo.get_latest_by_fingerprint(request_fingerprint="fp", dataset_type="x")
    assert got_fp is not None

    fingerprint_stmt = db.execute.await_args.args[0]
    fingerprint_sql = str(fingerprint_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "analytics_export_jobs.request_fingerprint = 'fp'" in fingerprint_sql
    assert "analytics_export_jobs.dataset_type = 'x'" in fingerprint_sql
    assert "ORDER BY analytics_export_jobs.id DESC" in fingerprint_sql
