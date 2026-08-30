import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.services.ingestion_service.app.main import ingestion_idempotency_conflict_handler
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionIdempotencyConflictError,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result as _create_or_get_job_result,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    build_ingestion_payload_evidence as _build_ingestion_payload_evidence,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint as _ingestion_payload_fingerprint,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint_matches,
    source_safe_request_payload,
)

_FINGERPRINT_KEY_ID = "test-key"
_FINGERPRINT_SECRET = "test-ingestion-evidence-secret-32-bytes"
_FINGERPRINT_PREVIOUS_KEYS: dict[str, str] = {}
_TENANT_ID = "tenant-test"


def ingestion_payload_fingerprint(payload):
    return _ingestion_payload_fingerprint(
        payload,
        key_id=_FINGERPRINT_KEY_ID,
        hmac_secret=_FINGERPRINT_SECRET,
    )


def build_ingestion_payload_evidence(**kwargs):
    return _build_ingestion_payload_evidence(
        **kwargs,
        fingerprint_key_id=_FINGERPRINT_KEY_ID,
        fingerprint_hmac_secret=_FINGERPRINT_SECRET,
    )


async def create_or_get_job_result(**kwargs):
    return await _create_or_get_job_result(
        **kwargs,
        tenant_id=_TENANT_ID,
        fingerprint_key_id=_FINGERPRINT_KEY_ID,
        fingerprint_hmac_secret=_FINGERPRINT_SECRET,
        fingerprint_previous_keys=_FINGERPRINT_PREVIOUS_KEYS,
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


class _EmptySessionAsyncIterable:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


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


class _FakeLookupCreateSession(_FakeCreateSession):
    async def scalar(self, _stmt):
        return None


class _FakeExistingSession:
    def __init__(self, existing):
        self.existing = existing
        self.added_rows = []
        self.lock_calls = []
        self.scalar_statements = []

    def begin(self):
        return _FakeBegin()

    async def scalar(self, _stmt):
        self.scalar_statements.append(_stmt)
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
        tenant_id=_TENANT_ID,
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
        failure_status_code=None,
        failure_code=None,
        failure_detail=None,
        failure_headers=None,
        retry_count=0,
        last_retried_at=None,
        request_payload=request_payload,
        request_payload_fingerprint=request_payload_fingerprint,
    )


def test_ingestion_payload_fingerprint_is_canonical_for_key_order():
    left = {"transactions": [{"transaction_id": "T1", "amount": "10"}], "source": "api"}
    right = {"source": "api", "transactions": [{"amount": "10", "transaction_id": "T1"}]}

    assert ingestion_payload_fingerprint(left) == ingestion_payload_fingerprint(right)
    assert ingestion_payload_fingerprint(left).startswith("hmac-sha256:v1:test-key:")


def test_ingestion_payload_fingerprint_resists_low_entropy_dictionary_confirmation():
    payload = {"transaction_ids": ["T1"]}

    fingerprint = ingestion_payload_fingerprint(payload)
    plain_digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert fingerprint != f"sha256:{plain_digest}"
    assert plain_digest not in fingerprint


def test_ingestion_payload_fingerprint_verifies_retained_rotation_key_and_fails_unknown_key():
    payload = {"transaction_ids": ["T1"]}
    prior = _ingestion_payload_fingerprint(
        payload,
        key_id="prior-key",
        hmac_secret="prior-ingestion-evidence-secret-32-bytes",
    )
    assert prior is not None

    assert ingestion_payload_fingerprint_matches(
        stored_fingerprint=prior,
        payload=payload,
        secrets_by_key_id={"prior-key": "prior-ingestion-evidence-secret-32-bytes"},
    )
    assert not ingestion_payload_fingerprint_matches(
        stored_fingerprint=prior,
        payload=payload,
        secrets_by_key_id={"test-key": _FINGERPRINT_SECRET},
    )
    assert not ingestion_payload_fingerprint_matches(
        stored_fingerprint=f"sha256:{'a' * 64}",
        payload=payload,
        secrets_by_key_id={"test-key": _FINGERPRINT_SECRET},
    )


def test_source_safe_payload_projection_redacts_sensitive_values_before_fingerprinting():
    left = {"authorization": "Bearer first-token", "records": [{"id": "1"}]}
    right = {"authorization": "Bearer second-token", "records": [{"id": "1"}]}

    assert ingestion_payload_fingerprint(
        source_safe_request_payload(left)
    ) == ingestion_payload_fingerprint(source_safe_request_payload(right))


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


def test_sensitive_family_retains_only_full_non_reversible_fingerprint() -> None:
    observed_at = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)
    payload = {
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "amount": "1000000.00",
            }
        ]
    }

    evidence = build_ingestion_payload_evidence(
        endpoint="/ingest/transactions",
        entity_type="transaction",
        payload=payload,
        observed_at=observed_at,
    )

    assert evidence.request_payload is None
    assert evidence.request_payload_fingerprint == ingestion_payload_fingerprint(payload)
    assert evidence.classification == "restricted"
    assert evidence.durable_representation == "fingerprint_only"
    assert evidence.replay_eligible is False
    assert evidence.partial_replay_eligible is False
    assert evidence.replay_expires_at is None
    assert evidence.retention_authority == "lotus-core#708"


def test_source_safe_internal_family_has_bounded_replay_payload() -> None:
    observed_at = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)
    payload = {
        "instruments": [
            {
                "security_id": "US0378331005",
                "authorization": "Bearer source-secret",
            }
        ]
    }

    evidence = build_ingestion_payload_evidence(
        endpoint="/ingest/instruments",
        entity_type="instrument",
        payload=payload,
        observed_at=observed_at,
    )

    assert evidence.request_payload == {
        "instruments": [
            {
                "security_id": "US0378331005",
                "authorization": "***REDACTED***",
            }
        ]
    }
    assert evidence.request_payload_fingerprint == ingestion_payload_fingerprint(payload)
    assert evidence.classification == "internal"
    assert evidence.durable_representation == "source_safe_replay"
    assert evidence.replay_eligible is True
    assert evidence.partial_replay_eligible is True
    assert evidence.replay_expires_at == datetime(2026, 8, 15, 4, 0, tzinfo=UTC)


def test_payload_evidence_rejects_unknown_endpoint_entity_or_naive_time() -> None:
    with pytest.raises(KeyError, match="Unclassified ingestion endpoint"):
        build_ingestion_payload_evidence(
            endpoint="/ingest/unknown",
            entity_type="unknown",
            payload={"records": []},
            observed_at=datetime(2026, 8, 14, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="entity mismatch"):
        build_ingestion_payload_evidence(
            endpoint="/ingest/instruments",
            entity_type="portfolio",
            payload={"instruments": []},
            observed_at=datetime(2026, 8, 14, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_ingestion_payload_evidence(
            endpoint="/ingest/instruments",
            entity_type="instrument",
            payload={"instruments": []},
            observed_at=datetime(2026, 8, 14),
        )


@pytest.mark.asyncio
async def test_create_or_get_job_rejects_missing_request_evidence_before_database_access() -> None:
    def unexpected_session_factory():
        pytest.fail("database access must not occur without request evidence")

    with pytest.raises(ValueError, match="require request payload evidence"):
        await create_or_get_job_result(
            job_id="job_missing_evidence",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=0,
            idempotency_key=None,
            correlation_id="corr_missing_evidence",
            request_id="req_missing_evidence",
            trace_id="trace_missing_evidence",
            request_payload=None,
            session_factory=unexpected_session_factory,
        )


@pytest.mark.asyncio
async def test_create_or_get_job_fails_closed_when_database_session_is_unavailable() -> None:
    with pytest.raises(RuntimeError, match="unavailable database session"):
        await create_or_get_job_result(
            job_id="job_without_session",
            endpoint="/ingest/transactions",
            entity_type="transaction",
            accepted_count=1,
            idempotency_key=None,
            correlation_id="corr_without_session",
            request_id="req_without_session",
            trace_id="trace_without_session",
            request_payload={"transactions": [{"transaction_id": "T1"}]},
            session_factory=_EmptySessionAsyncIterable,
        )


@pytest.mark.asyncio
async def test_create_or_get_job_persists_fingerprint_only_policy_for_transaction():
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
    assert result.job.request_payload_policy_version == "ingestion-evidence-policy.v1"
    assert result.job.request_payload_classification == "restricted"
    assert result.job.request_payload_representation == "fingerprint_only"
    assert result.job.request_payload_replay_eligible is False
    row = session.added_rows[0]
    assert row.request_payload is None
    assert row.request_payload_fingerprint == ingestion_payload_fingerprint(payload)
    assert row.request_payload_policy_version == "ingestion-evidence-policy.v1"
    assert row.request_payload_classification == "restricted"
    assert row.request_payload_representation == "fingerprint_only"
    assert row.request_payload_replay_eligible is False
    assert row.request_payload_partial_replay_eligible is False
    assert row.request_payload_replay_expires_at is None
    assert row.request_payload_retention_authority == "lotus-core#708"
    assert session.lock_calls == []
    assert payload["transactions"][0]["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_create_or_get_job_persists_expiring_source_safe_instrument_replay():
    session = _FakeCreateSession()
    payload = {
        "instruments": [
            {
                "instrument_id": "BOND_1",
                "name": "Singapore Government Bond",
                "authorization": "Bearer secret-token",
            }
        ]
    }

    await create_or_get_job_result(
        job_id="job_instrument",
        endpoint="/ingest/instruments",
        entity_type="instrument",
        accepted_count=1,
        idempotency_key=None,
        correlation_id="corr_1",
        request_id="req_1",
        trace_id="trace_1",
        request_payload=payload,
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    row = session.added_rows[0]
    assert row.request_payload["instruments"][0]["authorization"] == "***REDACTED***"
    assert row.request_payload_fingerprint == ingestion_payload_fingerprint(payload)
    assert row.request_payload_representation == "source_safe_replay"
    assert row.request_payload_replay_eligible is True
    assert row.request_payload_partial_replay_eligible is True
    assert row.request_payload_replay_expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_create_or_get_job_locks_before_creating_new_idempotent_job() -> None:
    session = _FakeLookupCreateSession()
    payload = {"transactions": [{"transaction_id": "T1", "portfolio_id": "P1"}]}

    result = await create_or_get_job_result(
        job_id="job_new_idempotent",
        endpoint="/ingest/transactions",
        entity_type="transaction",
        accepted_count=1,
        idempotency_key="idem_new",
        correlation_id="corr_new",
        request_id="req_new",
        trace_id="trace_new",
        request_payload=payload,
        session_factory=lambda: _SingleSessionAsyncIterable(session),
    )

    assert result.created is True
    assert result.job.job_id == "job_new_idempotent"
    assert session.lock_calls == [
        (
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))",
            {"lock_key": "tenant-test|/ingest/transactions|idem_new"},
        )
    ]
    assert session.added_rows[0].request_payload_fingerprint == ingestion_payload_fingerprint(
        payload
    )


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
            {"lock_key": "tenant-test|/ingest/transactions|idem_1"},
        )
    ]
    compiled_lookup = session.scalar_statements[0].compile()
    assert "ingestion_jobs.tenant_id = :tenant_id_1" in str(compiled_lookup)
    assert compiled_lookup.params["tenant_id_1"] == "tenant-test"
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
            {"lock_key": "tenant-test|/ingest/transactions|idem_1"},
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

    assert ingestion_payload_fingerprint(
        source_safe_request_payload(existing_payload)
    ) == ingestion_payload_fingerprint(source_safe_request_payload(requested_payload))
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
