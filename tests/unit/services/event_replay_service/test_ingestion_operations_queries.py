from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.ingestion_operations_queries import (
    IngestionOperationsNotFound,
    IngestionOperationsQueryService,
)


def _query_service(*, ingestion_job_service: MagicMock | None = None):
    return IngestionOperationsQueryService(
        ingestion_job_service=ingestion_job_service or MagicMock()
    )


@pytest.mark.asyncio
async def test_list_jobs_returns_page_with_total_and_next_cursor() -> None:
    submitted_from = datetime(2026, 7, 4, 9, 0)
    submitted_to = datetime(2026, 7, 4, 10, 0)
    jobs = [SimpleNamespace(job_id="job-001"), SimpleNamespace(job_id="job-002")]
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(return_value=(jobs, "job-002"))

    page = await _query_service(ingestion_job_service=ingestion_job_service).list_jobs(
        status="failed",
        entity_type="transaction",
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        cursor="job-000",
        limit=2,
    )

    assert page.jobs == jobs
    assert page.total == 2
    assert page.next_cursor == "job-002"
    ingestion_job_service.list_jobs.assert_awaited_once_with(
        status="failed",
        entity_type="transaction",
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        cursor="job-000",
        limit=2,
    )


@pytest.mark.asyncio
async def test_list_job_failures_requires_existing_job() -> None:
    failures = [SimpleNamespace(phase="publish"), SimpleNamespace(phase="bookkeeping")]
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=SimpleNamespace(job_id="job-001"))
    ingestion_job_service.list_failures = AsyncMock(return_value=failures)

    page = await _query_service(ingestion_job_service=ingestion_job_service).list_job_failures(
        job_id="job-001", limit=10
    )

    assert page.failures == failures
    assert page.total == 2
    ingestion_job_service.list_failures.assert_awaited_once_with(job_id="job-001", limit=10)


@pytest.mark.asyncio
async def test_list_job_failures_not_found_uses_governed_code() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job = AsyncMock(return_value=None)
    ingestion_job_service.list_failures = AsyncMock()

    with pytest.raises(IngestionOperationsNotFound) as exc_info:
        await _query_service(ingestion_job_service=ingestion_job_service).list_job_failures(
            job_id="missing-job",
            limit=10,
        )

    assert exc_info.value.code == "INGESTION_JOB_NOT_FOUND"
    assert exc_info.value.message == "Ingestion job 'missing-job' was not found."
    ingestion_job_service.list_failures.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_job_record_status_not_found_uses_governed_code() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_job_record_status = AsyncMock(return_value=None)

    with pytest.raises(IngestionOperationsNotFound) as exc_info:
        await _query_service(ingestion_job_service=ingestion_job_service).get_job_record_status(
            "missing-job"
        )

    assert exc_info.value.code == "INGESTION_JOB_NOT_FOUND"
    assert exc_info.value.message == "Ingestion job 'missing-job' was not found."


@pytest.mark.asyncio
async def test_list_consumer_dlq_events_returns_page_with_filters() -> None:
    events = [SimpleNamespace(event_id="dlq-001")]
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_consumer_dlq_events = AsyncMock(return_value=events)

    page = await _query_service(
        ingestion_job_service=ingestion_job_service
    ).list_consumer_dlq_events(
        limit=25,
        original_topic="transactions.raw.received",
        consumer_group="persistence-service-group",
    )

    assert page.events == events
    assert page.total == 1
    ingestion_job_service.list_consumer_dlq_events.assert_awaited_once_with(
        limit=25,
        original_topic="transactions.raw.received",
        consumer_group="persistence-service-group",
    )


@pytest.mark.asyncio
async def test_list_replay_audits_returns_page_with_filters() -> None:
    audits = [SimpleNamespace(replay_id="replay-001")]
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_replay_audits = AsyncMock(return_value=audits)

    page = await _query_service(ingestion_job_service=ingestion_job_service).list_replay_audits(
        limit=25,
        recovery_path="consumer_dlq_replay",
        replay_status="replayed",
        replay_fingerprint="fp-001",
        job_id="job-001",
    )

    assert page.audits == audits
    assert page.total == 1
    ingestion_job_service.list_replay_audits.assert_awaited_once_with(
        limit=25,
        recovery_path="consumer_dlq_replay",
        replay_status="replayed",
        replay_fingerprint="fp-001",
        job_id="job-001",
    )


@pytest.mark.asyncio
async def test_get_replay_audit_not_found_uses_governed_code() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.get_replay_audit = AsyncMock(return_value=None)

    with pytest.raises(IngestionOperationsNotFound) as exc_info:
        await _query_service(ingestion_job_service=ingestion_job_service).get_replay_audit(
            "missing-replay"
        )

    assert exc_info.value.code == "INGESTION_REPLAY_AUDIT_NOT_FOUND"
    assert exc_info.value.message == "Replay audit 'missing-replay' was not found."
