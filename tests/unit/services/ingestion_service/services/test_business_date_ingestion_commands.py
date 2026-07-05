from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.DTOs.business_date_dto import (
    BusinessDateIngestionRequest,
)
from src.services.ingestion_service.app.services.business_date_ingestion_commands import (
    BusinessDateBookkeepingFailed,
    BusinessDateIngestionCommand,
    BusinessDateIngestionCommandError,
    BusinessDateIngestionCommandHandler,
    BusinessDateIngestionPublishUnavailable,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    IngestionJobCreateResult,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionPublishError

pytestmark = pytest.mark.asyncio


class _Policy:
    def __init__(self) -> None:
        self.requests: list[BusinessDateIngestionRequest] = []

    async def validate(self, request: BusinessDateIngestionRequest) -> None:
        self.requests.append(request)


class _IngestionService:
    def __init__(self) -> None:
        self.publish_business_dates = AsyncMock()


class _JobService:
    def __init__(self, *, created: bool = True, mark_queued_result: bool = True) -> None:
        self.created = created
        self.mark_queued_result = mark_queued_result
        self.assert_ingestion_writable = AsyncMock()
        self.create_or_get_job = AsyncMock(side_effect=self._create_or_get_job)
        self.mark_failed = AsyncMock()
        self.mark_queued = AsyncMock(side_effect=self._mark_queued)
        self.record_failure_observation = AsyncMock()

    async def _create_or_get_job(self, **kwargs):
        job = SimpleNamespace(
            job_id="job-business-date",
            accepted_count=kwargs["accepted_count"],
            submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        if not self.created:
            job.job_id = "job-existing"
            job.accepted_count = 3
        return IngestionJobCreateResult(job=job, created=self.created)

    async def _mark_queued(self, _job_id: str) -> bool:
        return self.mark_queued_result


def _request() -> BusinessDateIngestionRequest:
    return BusinessDateIngestionRequest(
        business_dates=[{"business_date": "2026-03-10", "calendar_code": "GLOBAL"}]
    )


def _handler(
    *,
    ingestion_service: _IngestionService | None = None,
    job_service: _JobService | None = None,
    policy: _Policy | None = None,
) -> BusinessDateIngestionCommandHandler:
    return BusinessDateIngestionCommandHandler(
        ingestion_service=ingestion_service or _IngestionService(),
        ingestion_job_service=job_service or _JobService(),
        business_date_policy=policy or _Policy(),
    )


async def test_business_date_command_publishes_and_marks_job_queued() -> None:
    ingestion_service = _IngestionService()
    job_service = _JobService()
    policy = _Policy()
    handler = _handler(
        ingestion_service=ingestion_service,
        job_service=job_service,
        policy=policy,
    )

    result = await handler.ingest_business_dates(
        BusinessDateIngestionCommand(
            request=_request(),
            endpoint="/ingest/business-dates",
            idempotency_key="idem-business-dates",
        )
    )

    assert result.replayed is False
    assert result.job_id == "job-business-date"
    assert result.accepted_count == 1
    assert policy.requests == [_request()]
    job_service.create_or_get_job.assert_awaited_once()
    create_kwargs = job_service.create_or_get_job.await_args.kwargs
    assert create_kwargs["endpoint"] == "/ingest/business-dates"
    assert create_kwargs["entity_type"] == "business_date"
    assert create_kwargs["idempotency_key"] == "idem-business-dates"
    ingestion_service.publish_business_dates.assert_awaited_once()
    job_service.mark_queued.assert_awaited_once_with("job-business-date")


async def test_business_date_command_replays_duplicate_without_publish_or_queue() -> None:
    ingestion_service = _IngestionService()
    job_service = _JobService(created=False)
    handler = _handler(ingestion_service=ingestion_service, job_service=job_service)

    result = await handler.ingest_business_dates(
        BusinessDateIngestionCommand(
            request=_request(),
            endpoint="/ingest/business-dates",
            idempotency_key="idem-business-dates",
        )
    )

    assert result.replayed is True
    assert result.job_id == "job-existing"
    assert result.accepted_count == 3
    ingestion_service.publish_business_dates.assert_not_awaited()
    job_service.mark_queued.assert_not_awaited()


async def test_business_date_command_marks_failed_for_publish_error() -> None:
    ingestion_service = _IngestionService()
    publish_error = IngestionPublishError(
        "failed to publish business date",
        failed_record_keys=["GLOBAL|2026-03-10"],
    )
    ingestion_service.publish_business_dates.side_effect = publish_error
    job_service = _JobService()
    handler = _handler(ingestion_service=ingestion_service, job_service=job_service)

    with pytest.raises(BusinessDateIngestionPublishUnavailable) as exc_info:
        await handler.ingest_business_dates(
            BusinessDateIngestionCommand(
                request=_request(),
                endpoint="/ingest/business-dates",
                idempotency_key="idem-business-dates",
            )
        )

    assert exc_info.value.publish_error is publish_error
    assert exc_info.value.job_id == "job-business-date"
    job_service.mark_failed.assert_awaited_once_with(
        "job-business-date",
        "failed to publish business date",
        failed_record_keys=["GLOBAL|2026-03-10"],
    )
    job_service.mark_queued.assert_not_awaited()


async def test_business_date_command_records_bookkeeping_failure_when_queue_rejected() -> None:
    job_service = _JobService(mark_queued_result=False)
    handler = _handler(job_service=job_service)

    with pytest.raises(BusinessDateBookkeepingFailed) as exc_info:
        await handler.ingest_business_dates(
            BusinessDateIngestionCommand(
                request=_request(),
                endpoint="/ingest/business-dates",
                idempotency_key="idem-business-dates",
            )
        )

    assert exc_info.value.job_id == "job-business-date"
    assert exc_info.value.published_record_count == 1
    job_service.record_failure_observation.assert_awaited_once_with(
        "job-business-date",
        "job queue transition was rejected",
        failure_phase="queue_bookkeeping",
    )


async def test_business_date_command_maps_mode_denial_to_typed_error() -> None:
    job_service = _JobService()
    job_service.assert_ingestion_writable.side_effect = PermissionError("writes paused")
    handler = _handler(job_service=job_service)

    with pytest.raises(BusinessDateIngestionCommandError) as exc_info:
        await handler.ingest_business_dates(
            BusinessDateIngestionCommand(
                request=_request(),
                endpoint="/ingest/business-dates",
                idempotency_key=None,
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "writes paused",
    }
