from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.services.reference_data_ingestion_commands import (
    ReferenceDataBookkeepingFailed,
    ReferenceDataIngestionCommand,
    ReferenceDataIngestionCommandError,
    ReferenceDataIngestionCommandHandler,
)


def _job_result(*, created: bool = True, job_id: str = "ref-job-1", accepted_count: int = 2):
    return SimpleNamespace(
        created=created,
        job=SimpleNamespace(job_id=job_id, accepted_count=accepted_count),
    )


def _registry_command(*, persist_side_effect=None):
    command = SimpleNamespace(
        endpoint="/ingest/reference",
        entity_type="reference_data",
        accepted_count=lambda request: len(request.records),
        request_payload=lambda request: {"records": request.records},
        persist=AsyncMock(side_effect=persist_side_effect),
    )
    return command


def _handler() -> ReferenceDataIngestionCommandHandler:
    reference_data_service = SimpleNamespace()
    job_service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=_job_result()),
        mark_failed=AsyncMock(),
        mark_queued=AsyncMock(return_value=True),
        record_failure_observation=AsyncMock(),
    )
    return ReferenceDataIngestionCommandHandler(
        reference_data_service=reference_data_service,
        ingestion_job_service=job_service,
    )


@pytest.mark.asyncio
async def test_reference_data_command_persists_and_marks_queued() -> None:
    handler = _handler()
    registry_command = _registry_command()
    request = SimpleNamespace(records=[{"id": "R1"}, {"id": "R2"}])

    result = await handler.ingest_reference_data(
        ReferenceDataIngestionCommand(
            endpoint="/ingest/reference",
            idempotency_key="ref-key",
            registry_command=registry_command,
            request=request,
        )
    )

    assert result.job_id == "ref-job-1"
    assert result.accepted_count == 2
    registry_command.persist.assert_awaited_once_with(handler.reference_data_service, request)
    handler.ingestion_job_service.mark_queued.assert_awaited_once_with("ref-job-1")


@pytest.mark.asyncio
async def test_reference_data_command_replay_skips_persist() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="ref-job-replay",
        accepted_count=3,
    )
    registry_command = _registry_command()

    result = await handler.ingest_reference_data(
        ReferenceDataIngestionCommand(
            endpoint="/ingest/reference",
            idempotency_key="ref-replay",
            registry_command=registry_command,
            request=SimpleNamespace(records=[{"id": "R1"}]),
        )
    )

    assert result.replayed is True
    assert result.job_id == "ref-job-replay"
    assert result.accepted_count == 3
    registry_command.persist.assert_not_awaited()
    handler.ingestion_job_service.mark_queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_data_command_marks_failed_on_persist_error() -> None:
    handler = _handler()
    registry_command = _registry_command(persist_side_effect=RuntimeError("db unavailable"))

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/reference",
                idempotency_key=None,
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "REFERENCE_DATA_PERSIST_FAILED",
        "message": "db unavailable",
        "job_id": "ref-job-1",
    }
    handler.ingestion_job_service.mark_failed.assert_awaited_once_with(
        "ref-job-1",
        "db unavailable",
        failure_phase="persist",
    )


@pytest.mark.asyncio
async def test_reference_data_command_raises_bookkeeping_failure_when_queue_rejected() -> None:
    handler = _handler()
    handler.ingestion_job_service.mark_queued.return_value = False

    with pytest.raises(ReferenceDataBookkeepingFailed) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/reference",
                idempotency_key=None,
                registry_command=_registry_command(),
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.job_id == "ref-job-1"
    handler.ingestion_job_service.record_failure_observation.assert_awaited_once()
