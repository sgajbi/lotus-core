from datetime import UTC, datetime
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

    updated = await service.mark_queued("job_mark_queued", tenant_id="tenant-test")

    assert updated is True
    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.tenant_id =" in compiled_sql
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

    updated = await service.mark_queued("job_mark_queued", tenant_id="tenant-test")

    assert updated is False
    assert len(session.executed_statements) == 1


async def test_mark_failed_returns_false_without_recording_when_expected_status_is_stale(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(returned_row=None)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    updated = await service.mark_failed(
        "job_already_terminal",
        failure_reason="late failure observation",
        failure_phase="publish",
        tenant_id="tenant-test",
    )

    assert updated is False
    assert len(session.executed_statements) == 1
    assert session.added_rows == []


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
        failure_detail={
            "dependency": "kafka",
            "retryable": True,
            "message": "password=secret at kafka.internal:9093",
            "request_payload": {"client_email": "client@example.com"},
        },
        failure_headers={"Retry-After": "30", "Authorization": "Bearer secret"},
        tenant_id="tenant-test",
    )

    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "ingestion_jobs.tenant_id = :tenant_id_1" in compiled_sql
    assert "failure_status_code=:failure_status_code" in compiled_sql
    assert "failure_code=:failure_code" in compiled_sql
    assert "failure_detail=:failure_detail" in compiled_sql
    assert "failure_headers=:failure_headers" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql
    compiled_params = session.executed_statements[0].compile().params
    assert compiled_params["failure_reason"] == (
        "Ingestion publishing failed before durable queue confirmation."
    )
    assert compiled_params["failure_detail"] == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Ingestion publishing failed before durable queue confirmation.",
        "dependency": "kafka",
        "retryable": True,
    }
    assert compiled_params["failure_headers"] == {"Retry-After": "30"}
    assert "secret" not in repr(compiled_params)
    assert "client@example.com" not in repr(compiled_params)

    assert len(session.added_rows) == 1
    failure_row = session.added_rows[0]
    assert isinstance(failure_row, DBIngestionJobFailure)
    assert failure_row.job_id == "job_mark_failed"
    assert failure_row.failure_phase == "retry_publish"
    assert (
        failure_row.failure_reason
        == "Ingestion publishing failed before durable queue confirmation."
    )
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

    await service.mark_retried("job_mark_retried", tenant_id="tenant-test")

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


async def test_mark_retried_returns_false_when_job_is_not_retryable(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(returned_row=None)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    updated = await service.mark_retried(
        "job_not_retryable",
        tenant_id="tenant-test",
    )

    assert updated is False
    assert len(session.executed_statements) == 1


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

    updated = await service.mark_retried_and_queued("job_mark_retried", tenant_id="tenant-test")

    assert updated is True
    assert len(session.executed_statements) == 1
    compiled_sql = str(session.executed_statements[0])
    assert "UPDATE ingestion_jobs" in compiled_sql
    assert "ingestion_jobs.status IN" in compiled_sql
    assert "ingestion_jobs.tenant_id =" in compiled_sql
    assert "ingestion_jobs.tenant_id = :tenant_id_1" in compiled_sql
    assert "status=:status" in compiled_sql
    assert (
        "retry_count=(coalesce(ingestion_jobs.retry_count, :coalesce_1) + :coalesce_2)"
        in compiled_sql
    )
    assert "last_retried_at=:last_retried_at" in compiled_sql
    assert "failure_detail=NULL" in compiled_sql
    assert "failure_headers=NULL" in compiled_sql
    assert "RETURNING ingestion_jobs.endpoint, ingestion_jobs.entity_type" in compiled_sql


async def test_mark_retried_and_queued_returns_false_when_job_is_not_retryable(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(returned_row=None)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    updated = await service.mark_retried_and_queued("job_not_retryable", tenant_id="tenant-test")

    assert updated is False
    assert len(session.executed_statements) == 1


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
    assert failure_row.failure_reason == (
        "Ingestion work completed, but job bookkeeping did not complete afterward."
    )
    assert session.returned_row.failure_status_code == 500
    assert session.returned_row.failure_code == "INGESTION_JOB_BOOKKEEPING_FAILED"
    assert session.returned_row.failure_detail == {
        "code": "INGESTION_JOB_BOOKKEEPING_FAILED",
        "message": ("Ingestion work completed, but job bookkeeping did not complete afterward."),
        "work_state": "published",
        "retry_safe": False,
    }


async def test_record_failure_observation_ignores_unknown_job(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(returned_row=None)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    await service.record_failure_observation(
        "job_missing",
        "late observation for an unknown job",
        failure_phase="queue_bookkeeping",
    )

    assert len(session.executed_statements) == 1
    assert session.added_rows == []


def _persisted_job(*, request_payload: object) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job_replayable",
        tenant_id="tenant-test",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status="failed",
        accepted_count=1,
        idempotency_key="idem-001",
        correlation_id="corr-001",
        request_id="req-001",
        trace_id="trace-001",
        submitted_at=datetime(2026, 7, 28, tzinfo=UTC),
        completed_at=datetime(2026, 7, 28, tzinfo=UTC),
        failure_reason="publish failed",
        failure_status_code=503,
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={"retryable": True},
        failure_headers={"Retry-After": "30"},
        retry_count=0,
        last_retried_at=None,
        request_payload=request_payload,
        request_payload_policy_version="ingestion-evidence-policy.v1",
        request_payload_representation="source_safe_replay",
        request_payload_replay_eligible=True,
        request_payload_partial_replay_eligible=True,
        request_payload_replay_expires_at=datetime(2026, 7, 29, tzinfo=UTC),
        request_payload_retention_authority="lotus-core#708",
    )


@pytest.mark.parametrize(
    ("persisted_row", "expected_job_id"),
    [
        (
            _persisted_job(request_payload={"transactions": [{"transaction_id": "tx-001"}]}),
            "job_replayable",
        ),
        (None, None),
    ],
)
async def test_get_job_maps_persisted_row_or_returns_none(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
    persisted_row: SimpleNamespace | None,
    expected_job_id: str | None,
) -> None:
    session = _FakeSession(returned_row=persisted_row)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    response = await service.get_job("job_replayable", tenant_id="tenant-test")

    assert (response.job_id if response else None) == expected_job_id
    if response is not None:
        assert response.tenant_id == "tenant-test"
    assert len(session.executed_statements) == 1
    assert "ingestion_jobs.tenant_id = :tenant_id_1" in str(session.executed_statements[0])


@pytest.mark.parametrize(
    ("persisted_row", "expected_payload"),
    [
        (
            _persisted_job(request_payload={"transactions": [{"transaction_id": "tx-001"}]}),
            {"transactions": [{"transaction_id": "tx-001"}]},
        ),
        (_persisted_job(request_payload="invalid-legacy-payload"), None),
        (None, None),
    ],
)
async def test_get_job_replay_context_maps_only_object_payloads(
    service: IngestionJobService,
    monkeypatch: pytest.MonkeyPatch,
    persisted_row: SimpleNamespace | None,
    expected_payload: dict | None,
) -> None:
    session = _FakeSession(returned_row=persisted_row)
    monkeypatch.setattr(
        service_module,
        "get_async_db_session",
        make_single_session_getter(session),
    )

    response = await service.get_job_replay_context("job_replayable", tenant_id="tenant-test")

    if persisted_row is None:
        assert response is None
    else:
        assert response is not None
        assert response.tenant_id == "tenant-test"
        assert response.request_payload == expected_payload
        assert response.request_payload_policy_version == "ingestion-evidence-policy.v1"
        assert response.request_payload_replay_eligible is True
        assert response.request_payload_replay_expires_at == datetime(2026, 7, 29, tzinfo=UTC)
    assert len(session.executed_statements) == 1
    assert "ingestion_jobs.tenant_id = :tenant_id_1" in str(session.executed_statements[0])


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
            tenant_id="tenant-test",
            failure_status_code=failure_status_code,
            failure_code=failure_code,
            failure_detail=failure_detail,
        )

    assert session.executed_statements == []
