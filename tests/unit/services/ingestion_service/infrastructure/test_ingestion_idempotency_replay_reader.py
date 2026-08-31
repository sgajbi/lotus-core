from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.infrastructure.ingestion_idempotency_replay_reader import (
    SqlAlchemyIngestionIdempotencyReplayReader,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint as _ingestion_payload_fingerprint,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    source_safe_request_payload,
)

pytestmark = pytest.mark.asyncio

_ACTIVE_KEY_ID = "test-active"
_ACTIVE_SECRET = "test-active-ingestion-evidence-secret"
_PREVIOUS_KEY_ID = "test-previous"
_PREVIOUS_SECRET = "test-previous-ingestion-evidence-secret"
_KEYRING = {
    _ACTIVE_KEY_ID: _ACTIVE_SECRET,
    _PREVIOUS_KEY_ID: _PREVIOUS_SECRET,
}


def ingestion_payload_fingerprint(payload, *, key_id=_ACTIVE_KEY_ID, secret=_ACTIVE_SECRET):
    return _ingestion_payload_fingerprint(payload, key_id=key_id, hmac_secret=secret)


def _job(
    *,
    request_payload: object,
    request_payload_fingerprint: str | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-existing",
        endpoint="/reprocess/transactions",
        entity_type="reprocessing_request",
        status="queued",
        accepted_count=2,
        idempotency_key="idem-reprocess",
        correlation_id="corr-existing",
        request_id="req-existing",
        trace_id="trace-existing",
        submitted_at=datetime(2026, 7, 17, tzinfo=UTC),
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


def _reader(existing: object | None):
    db = SimpleNamespace(scalar=AsyncMock(return_value=existing))
    return SqlAlchemyIngestionIdempotencyReplayReader(db, fingerprint_keyring=_KEYRING), db


async def test_missing_idempotency_key_does_not_query_store() -> None:
    reader, db = _reader(None)

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key=None,
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is None
    db.scalar.assert_not_awaited()


async def test_missing_job_returns_no_replay() -> None:
    reader, db = _reader(None)

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is None
    db.scalar.assert_awaited_once()
    assert "ingestion_jobs.tenant_id =" in str(db.scalar.await_args.args[0])


async def test_matching_current_fingerprint_returns_established_job() -> None:
    payload = {"transaction_ids": ["T1", "T2"]}
    reader, _ = _reader(
        _job(
            request_payload=source_safe_request_payload(payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(payload),
        )
    )

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is not None
    assert result.job_id == "job-existing"
    assert result.accepted_count == 2
    assert result.status == "queued"
    assert result.failure_status_code is None


async def test_matching_retained_rotation_key_returns_established_job() -> None:
    payload = {"transaction_ids": ["T1", "T2"]}
    reader, _ = _reader(
        _job(
            request_payload=source_safe_request_payload(payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(
                payload,
                key_id=_PREVIOUS_KEY_ID,
                secret=_PREVIOUS_SECRET,
            ),
        )
    )

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload=payload,
    )

    assert result is not None
    assert result.job_id == "job-existing"


async def test_different_current_fingerprint_does_not_replay() -> None:
    existing_payload = {"transaction_ids": ["T1", "T2"]}
    reader, _ = _reader(
        _job(
            request_payload=source_safe_request_payload(existing_payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(existing_payload),
        )
    )

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T3"]},
    )

    assert result is None


@pytest.mark.parametrize(
    ("existing_payload", "requested_payload"),
    [
        (
            {"transaction_ids": ["T1"], "authorization": "Bearer old"},
            {"authorization": "Bearer new", "transaction_ids": ["T1"]},
        ),
        ({"transaction_ids": ["T1"]}, {"transaction_ids": ["T1"]}),
        ("unreadable-legacy-payload", None),
    ],
)
async def test_legacy_payload_without_full_fingerprint_fails_closed(
    existing_payload: object,
    requested_payload: dict | None,
) -> None:
    reader, _ = _reader(
        _job(
            request_payload=existing_payload,
            request_payload_fingerprint=None,
        )
    )

    result = await reader.find_matching_job(
        tenant_id="tenant-test",
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload=requested_payload,
    )

    assert result is None
