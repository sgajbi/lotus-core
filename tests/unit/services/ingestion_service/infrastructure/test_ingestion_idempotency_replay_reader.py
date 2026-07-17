from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.infrastructure.ingestion_idempotency_replay_reader import (
    SqlAlchemyIngestionIdempotencyReplayReader,
)
from src.services.ingestion_service.app.services.ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
    source_safe_request_payload,
)

pytestmark = pytest.mark.asyncio


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
        retry_count=0,
        last_retried_at=None,
        request_payload=request_payload,
        request_payload_fingerprint=request_payload_fingerprint,
    )


def _reader(existing: object | None):
    db = SimpleNamespace(scalar=AsyncMock(return_value=existing))
    return SqlAlchemyIngestionIdempotencyReplayReader(db), db


async def test_missing_idempotency_key_does_not_query_store() -> None:
    reader, db = _reader(None)

    result = await reader.find_matching_job(
        endpoint="/reprocess/transactions",
        idempotency_key=None,
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is None
    db.scalar.assert_not_awaited()


async def test_missing_job_returns_no_replay() -> None:
    reader, db = _reader(None)

    result = await reader.find_matching_job(
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is None
    db.scalar.assert_awaited_once()


async def test_matching_current_fingerprint_returns_established_job() -> None:
    payload = {"transaction_ids": ["T1", "T2"]}
    reader, _ = _reader(
        _job(
            request_payload=source_safe_request_payload(payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(payload),
        )
    )

    result = await reader.find_matching_job(
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T1", "T2"]},
    )

    assert result is not None
    assert result.job_id == "job-existing"
    assert result.accepted_count == 2


async def test_different_current_fingerprint_does_not_replay() -> None:
    existing_payload = {"transaction_ids": ["T1", "T2"]}
    reader, _ = _reader(
        _job(
            request_payload=source_safe_request_payload(existing_payload),
            request_payload_fingerprint=ingestion_payload_fingerprint(existing_payload),
        )
    )

    result = await reader.find_matching_job(
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload={"transaction_ids": ["T3"]},
    )

    assert result is None


@pytest.mark.parametrize(
    ("existing_payload", "requested_payload", "matches"),
    [
        (
            {"transaction_ids": ["T1"], "authorization": "Bearer old"},
            {"authorization": "Bearer new", "transaction_ids": ["T1"]},
            True,
        ),
        ({"transaction_ids": ["T1"]}, {"transaction_ids": ["T2"]}, False),
        ("unreadable-legacy-payload", None, True),
    ],
)
async def test_legacy_payload_comparison_preserves_source_safe_semantics(
    existing_payload: object,
    requested_payload: dict | None,
    matches: bool,
) -> None:
    reader, _ = _reader(
        _job(
            request_payload=existing_payload,
            request_payload_fingerprint=None,
        )
    )

    result = await reader.find_matching_job(
        endpoint="/reprocess/transactions",
        idempotency_key="idem-reprocess",
        request_payload=requested_payload,
    )

    assert (result is not None) is matches
