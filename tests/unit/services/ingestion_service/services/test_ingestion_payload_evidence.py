import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.main import ingestion_idempotency_conflict_handler
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionIdempotencyConflictError,
    create_or_get_job_result,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
    source_safe_payload_fingerprint,
    source_safe_request_payload,
)


class _SingleSessionAsyncIterable:
    def __init__(self, session):
        self._session = session
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return self._session


class _FakeBegin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeCreateSession:
    def __init__(self):
        self.added_rows = []
        self.lock_calls = []

    def begin(self):
        return _FakeBegin()

    def add(self, row):
        self.added_rows.append(row)

    async def execute(self, stmt, params=None):
        self.lock_calls.append((str(stmt), params))

    async def flush(self):
        row = self.added_rows[-1]
        row.submitted_at = datetime.now(UTC)
        row.completed_at = None
        row.failure_reason = None
        row.retry_count = 0
        row.last_retried_at = None


class _FakeExistingSession:
    def __init__(self, existing):
        self.existing = existing
        self.added_rows = []
        self.lock_calls = []

    def begin(self):
        return _FakeBegin()

    async def scalar(self, _stmt):
        return self.existing

    async def execute(self, stmt, params=None):
        self.lock_calls.append((str(stmt), params))

    def add(self, row):
        self.added_rows.append(row)


def _existing_job(
    *,
    request_payload: dict,
    request_payload_fingerprint: str | None = None,
    status: str = "accepted",
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job_existing",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        status=status,
        accepted_count=1,
        idempotency_key="idem_1",
        correlation_id="corr_existing",
        request_id="req_existing",
        trace_id="trace_existing",
        submitted_at=datetime.now(UTC),
        completed_at=None,
        failure_reason=None,
        retry_count=0,
        last_retried_at=None,
        request_payload=request_payload,
        request_payload_fingerprint=request_payload_fingerprint,
    )


def test_ingestion_payload_fingerprint_is_canonical_for_key_order():
    left = {"transactions": [{"transaction_id": "T1", "amount": "10"}], "source": "api"}
    right = {"source": "api", "transactions": [{"amount": "10", "transaction_id": "T1"}]}

    assert ingestion_payload_fingerprint(left) == ingestion_payload_fingerprint(right)
    assert ingestion_payload_fingerprint(left).startswith("sha256:")


def test_source_safe_payload_fingerprint_redacts_before_hashing_sensitive_values():
    left = {"authorization": "Bearer first-token", "records": [{"id": "1"}]}
    right = {"authorization": "Bearer second-token", "records": [{"id": "1"}]}

    assert source_safe_payload_fingerprint(left) == source_safe_payload_fingerprint(right)


def test_source_safe_request_payload_redacts_sensitive_values_without_mutating_input():
    payload = {
        "transactions": [
            {
                "transaction_id": "T1",
                "account_number": "123456789",
                "client_email": "client@example.com",
                "database_url": "postgresql://user:password@db/core",
            }
        ]
    }

    redacted = source_safe_request_payload(payload)

    assert payload["transactions"][0]["account_number"] == "123456789"
    assert redacted == {
        "transactions": [
            {
                "transaction_id": "T1",
                "account_number": "***REDACTED***",
                "client_email": "***REDACTED***",
                "database_url": "***REDACTED***",
            }
        ]
    }


@pytest.mark.asyncio
async def test_create_or_get_job_persists_source_safe_request_payload():
    session = _FakeCreateSession()
    payload = {
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "P1",
                "authorization": "Bearer secret-token",
            }
        ]
    }

    result = await create_or_get_job_result(
        job_id="job_1",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key=None,
        correlation_id="corr_1",
        request_id="req_1",
        trace_id="trace_1",
        request_payload=payload,
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert result.created is True
    assert session.added_rows[0].request_payload == {
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "P1",
                "authorization": "***REDACTED***",
            }
        ]
    }
    assert session.added_rows[0].request_payload_fingerprint == ingestion_payload_fingerprint(
        payload
    )
    assert session.lock_calls == []
    assert payload["transactions"][0]["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_create_or_get_job_replays_same_idempotency_key_and_same_payload():
    payload = {"transactions": [{"transaction_id": "T1", "amount": "10"}]}
    session = _FakeExistingSession(
        _existing_job(
            request_payload=source_safe_request_payload(payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(payload),
        )
    )

    result = await create_or_get_job_result(
        job_id="job_new",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem_1",
        correlation_id="corr_1",
        request_id="req_1",
        trace_id="trace_1",
        request_payload={"transactions": [{"amount": "10", "transaction_id": "T1"}]},
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert result.created is False
    assert result.job.job_id == "job_existing"
    assert session.lock_calls == [
        (
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))",
            {"lock_key": "/ingest/transactions|idem_1"},
        )
    ]
    assert session.added_rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["accepted", "queued", "failed"])
async def test_create_or_get_job_replays_existing_lifecycle_statuses(status: str):
    payload = {"transactions": [{"transaction_id": "T1", "amount": "10"}]}
    session = _FakeExistingSession(
        _existing_job(
            request_payload=source_safe_request_payload(payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(payload),
            status=status,
        )
    )

    result = await create_or_get_job_result(
        job_id="job_new",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem_1",
        correlation_id="corr_1",
        request_id="req_1",
        trace_id="trace_1",
        request_payload=payload,
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert result.created is False
    assert result.job.status == status
    assert session.added_rows == []


@pytest.mark.asyncio
async def test_create_or_get_job_rejects_same_idempotency_key_with_different_payload():
    existing_payload = {"transactions": [{"transaction_id": "T1"}]}
    session = _FakeExistingSession(
        _existing_job(
            request_payload=source_safe_request_payload(existing_payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(existing_payload),
        )
    )

    with pytest.raises(IngestionIdempotencyConflictError) as exc_info:
        await create_or_get_job_result(
            job_id="job_new",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=1,
            idempotency_key="idem_1",
            correlation_id="corr_1",
            request_id="req_1",
            trace_id="trace_1",
            request_payload={"transactions": [{"transaction_id": "T2"}]},
            session_factory=lambda: _SingleSessionAsyncIterable(session),
        )

    assert exc_info.value.endpoint == "/ingest/transactions"
    assert exc_info.value.idempotency_key == "idem_1"
    assert session.lock_calls == [
        (
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))",
            {"lock_key": "/ingest/transactions|idem_1"},
        )
    ]
    assert session.added_rows == []


@pytest.mark.asyncio
async def test_create_or_get_job_rejects_same_idempotency_key_with_different_sensitive_payload():
    existing_payload = {
        "authorization": "Bearer first-token",
        "transactions": [{"transaction_id": "T1"}],
    }
    requested_payload = {
        "authorization": "Bearer second-token",
        "transactions": [{"transaction_id": "T1"}],
    }
    session = _FakeExistingSession(
        _existing_job(
            request_payload=source_safe_request_payload(existing_payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(existing_payload),
        )
    )

    with pytest.raises(IngestionIdempotencyConflictError):
        await create_or_get_job_result(
            job_id="job_new",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=1,
            idempotency_key="idem_1",
            correlation_id="corr_1",
            request_id="req_1",
            trace_id="trace_1",
            request_payload=requested_payload,
            session_factory=lambda: _SingleSessionAsyncIterable(session),
        )

    assert source_safe_payload_fingerprint(existing_payload) == source_safe_payload_fingerprint(
        requested_payload
    )
    assert ingestion_payload_fingerprint(existing_payload) != ingestion_payload_fingerprint(
        requested_payload
    )
    assert session.added_rows == []


@pytest.mark.asyncio
async def test_ingestion_idempotency_conflict_handler_returns_deterministic_problem():
    response = await ingestion_idempotency_conflict_handler(
        None,
        IngestionIdempotencyConflictError(
            endpoint="/ingest/transactions",
            idempotency_key="idem_1",
        ),
    )

    assert response.status_code == 409
    assert json.loads(response.body) == {
        "detail": {
            "code": "INGESTION_IDEMPOTENCY_CONFLICT",
            "message": (
                "Ingestion idempotency key was reused for the same endpoint with a different "
                "payload."
            ),
            "endpoint": "/ingest/transactions",
            "idempotency_key": "idem_1",
        }
    }
