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

    async def scalar(self, statement):
        self.executed_statements.append(statement)
        return self.returned_row

    def add(self, row: object) -> None:
        self.added_rows.append(row)


@pytest.fixture
def service() -> IngestionJobService:
    return IngestionJobService()


async def test_mark_queued_uses_single_atomic_update(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession(returned_row=SimpleNamespace(status="accepted"))
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    updated = await service.mark_queued("job_mark_queued")

    assert updated is True
    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "status=:status" in compiled_sql
    assert "completed_at=:completed_at" in compiled_sql
    assert "failure_reason=:failure_reason" in compiled_sql
    assert "failure_detail=NULL" in compiled_sql
    assert "failure_headers=NULL" in compiled_sql
    assert "RETURNING ingestion_jobs.status" in compiled_sql


async def test_mark_queued_returns_false_when_expected_status_is_stale(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession(returned_row=None)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    updated = await service.mark_queued("job_mark_queued")

    assert updated is False
    assert len(session.executed_statements) == 1


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
        failure_status_code=503,
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={"dependency": "kafka", "retryable": True},
        failure_headers={"Retry-After": "30"},
    )

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "failure_status_code=:failure_status_code" in compiled_sql
    assert "failure_code=:failure_code" in compiled_sql
    assert "failure_detail=:failure_detail" in compiled_sql
    assert "failure_headers=:failure_headers" in compiled_sql
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
    assert "ingestion_jobs.status IN" in compiled_sql
    assert (
        "retry_count=(coalesce(ingestion_jobs.retry_count, :coalesce_1) + :coalesce_2)"
        in compiled_sql
    )
    assert "last_retried_at=:last_retried_at" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql


async def test_mark_retried_and_queued_is_single_expected_status_update(
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

    updated = await service.mark_retried_and_queued("job_mark_retried")

    assert updated is True
    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "status=:status" in compiled_sql
    assert (
        "retry_count=(coalesce(ingestion_jobs.retry_count, :coalesce_1) + :coalesce_2)"
        in compiled_sql
    )
    assert "last_retried_at=:last_retried_at" in compiled_sql
    assert "failure_detail=NULL" in compiled_sql
    assert "failure_headers=NULL" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql


async def test_record_failure_observation_preserves_job_status_and_records_failure(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _FakeSession(
        returned_row=SimpleNamespace(
            endpoint="transactions",
            entity_type="transaction",
            failure_status_code=None,
            failure_code=None,
            failure_detail=None,
            failure_headers=None,
        )
    )
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    await service.record_failure_observation(
        "job_publish_bookkeeping",
        "queue state write failed",
        failure_phase="queue_bookkeeping",
        failure_status_code=500,
        failure_code="INGESTION_JOB_BOOKKEEPING_FAILED",
        failure_detail={"work_state": "published", "retry_safe": False},
    )

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "SELECT ingestion_jobs.id" in compiled_sql

    assert len(session.added_rows) == 1
    failure_row = session.added_rows[0]
    assert isinstance(failure_row, DBIngestionJobFailure)
    assert failure_row.job_id == "job_publish_bookkeeping"
    assert failure_row.failure_phase == "queue_bookkeeping"
    assert failure_row.failure_reason == "queue state write failed"
    assert session.returned_row.failure_status_code == 500
    assert session.returned_row.failure_code == "INGESTION_JOB_BOOKKEEPING_FAILED"
    assert session.returned_row.failure_detail == {
        "work_state": "published",
        "retry_safe": False,
    }


@pytest.mark.parametrize(
    ("failure_status_code", "failure_code", "failure_detail", "expected_message"),
    [
        (None, "INGESTION_FAILED", None, "must be recorded together"),
        (500, None, None, "must be recorded together"),
        (200, "INGESTION_FAILED", None, "between 400 and 599"),
        (500, "  ", None, "must be non-empty"),
        (None, None, {"message": "orphan detail"}, "require both"),
    ],
)
async def test_mark_failed_rejects_incomplete_or_invalid_failure_outcome(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
    failure_status_code: int | None,
    failure_code: str | None,
    failure_detail: dict | None,
    expected_message: str,
) -> None:
    session = _FakeSession(
        returned_row=SimpleNamespace(endpoint="transactions", entity_type="transaction")
    )
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    with pytest.raises(ValueError, match=expected_message):
        await service.mark_failed(
            "job_mark_failed",
            failure_reason="publish failed",
            failure_status_code=failure_status_code,
            failure_code=failure_code,
            failure_detail=failure_detail,
        )

    assert session.executed_statements == []
