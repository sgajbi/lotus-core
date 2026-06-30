from datetime import UTC, datetime

import pytest

from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
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

    def begin(self):
        return _FakeBegin()

    def add(self, row):
        self.added_rows.append(row)

    async def flush(self):
        row = self.added_rows[-1]
        row.submitted_at = datetime.now(UTC)
        row.completed_at = None
        row.failure_reason = None
        row.retry_count = 0
        row.last_retried_at = None


def test_ingestion_payload_fingerprint_is_canonical_for_key_order():
    left = {"transactions": [{"transaction_id": "T1", "amount": "10"}], "source": "api"}
    right = {"source": "api", "transactions": [{"amount": "10", "transaction_id": "T1"}]}

    assert ingestion_payload_fingerprint(left) == ingestion_payload_fingerprint(right)
    assert ingestion_payload_fingerprint(left).startswith("sha256:")


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
    assert payload["transactions"][0]["authorization"] == "Bearer secret-token"
