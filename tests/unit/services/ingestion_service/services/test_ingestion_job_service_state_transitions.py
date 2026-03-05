from types import SimpleNamespace

import pytest
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure

from src.services.ingestion_service.app.services import ingestion_job_service as service_module
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService
from tests.unit.test_support.async_session_iter import make_single_session_getter

pytestmark = pytest.mark.asyncio


class _FakeBeginContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeResult:
    def __init__(self, row: object | None = None) -> None:
        self._row = row

    def first(self) -> object | None:
        return self._row


class _FakeSession:
    def __init__(self, returned_row: object | None = None) -> None:
        self.returned_row = returned_row
        self.executed_statements: list[object] = []
        self.added_rows: list[object] = []

    def begin(self) -> _FakeBeginContext:
        return _FakeBeginContext()

    async def execute(self, statement):
        self.executed_statements.append(statement)
        return _FakeResult(self.returned_row)

    def add(self, row: object) -> None:
        self.added_rows.append(row)


@pytest.fixture
def service() -> IngestionJobService:
    return IngestionJobService()


async def test_mark_queued_uses_single_atomic_update(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession()
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    await service.mark_queued("job_mark_queued")

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "status=:status" in compiled_sql
    assert "completed_at=:completed_at" in compiled_sql
    assert "failure_reason=:failure_reason" in compiled_sql


async def test_mark_failed_uses_atomic_update_and_records_failure(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession(
        returned_row=SimpleNamespace(endpoint="transactions", entity_type="transaction")
    )
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    await service.mark_failed(
        "job_mark_failed",
        failure_reason="publish failed",
        failure_phase="retry_publish",
        failed_record_keys=["tx-001"],
    )

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql

    assert len(session.added_rows) == 1
    failure_row = session.added_rows[0]
    assert isinstance(failure_row, DBIngestionJobFailure)
    assert failure_row.job_id == "job_mark_failed"
    assert failure_row.failure_phase == "retry_publish"
    assert failure_row.failure_reason == "publish failed"
    assert failure_row.failed_record_keys == ["tx-001"]


async def test_mark_retried_uses_atomic_increment_update(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession(
        returned_row=SimpleNamespace(endpoint="transactions", entity_type="transaction")
    )
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    await service.mark_retried("job_mark_retried")

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert (
        "retry_count=(coalesce(ingestion_jobs.retry_count, :coalesce_1) + :coalesce_2)"
        in compiled_sql
    )
    assert "last_retried_at=:last_retried_at" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql
