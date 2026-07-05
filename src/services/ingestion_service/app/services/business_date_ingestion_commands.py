from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..DTOs.business_date_dto import BusinessDateIngestionRequest
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import create_ingestion_job_id, get_request_lineage
from .business_date_ingestion_policy import (
    BusinessDateIngestionPolicy,
    BusinessDatePolicyViolation,
)
from .ingestion_job_service import IngestionJobService
from .ingestion_service import IngestionPublishError, IngestionService

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_SERVICE_UNAVAILABLE = 503


class BusinessDateIngestionCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "command failed"))))
        self.status_code = status_code
        self.detail = detail


class BusinessDateIngestionPublishUnavailable(Exception):
    def __init__(self, *, publish_error: IngestionPublishError, job_id: str) -> None:
        super().__init__(str(publish_error))
        self.publish_error = publish_error
        self.job_id = job_id


class BusinessDateBookkeepingFailed(Exception):
    def __init__(self, *, job_id: str, published_record_count: int) -> None:
        super().__init__("Business-date ingestion bookkeeping failed after publish.")
        self.job_id = job_id
        self.published_record_count = published_record_count
        self.failure_phase = "queue_bookkeeping"
        self.publish_state = "published"
        self.work_state = "published"


@dataclass(frozen=True, slots=True)
class BusinessDateIngestionCommand:
    request: BusinessDateIngestionRequest
    endpoint: str
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class BusinessDateIngestionCommandResult:
    message: str
    job_id: str
    accepted_count: int
    idempotency_key: str | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class BusinessDateIngestionCommandHandler:
    ingestion_service: IngestionService
    ingestion_job_service: IngestionJobService
    business_date_policy: BusinessDateIngestionPolicy

    async def ingest_business_dates(
        self,
        command: BusinessDateIngestionCommand,
    ) -> BusinessDateIngestionCommandResult:
        await self._assert_ingestion_writable()
        self._enforce_rate_limit(len(command.request.business_dates))
        await self._validate_request(command.request)

        accepted_count = len(command.request.business_dates)
        job_result = await self._create_ingestion_job(
            command=command,
            accepted_count=accepted_count,
        )
        if not job_result.created:
            return BusinessDateIngestionCommandResult(
                message="Duplicate ingestion request accepted via idempotency replay.",
                job_id=job_result.job.job_id,
                accepted_count=job_result.job.accepted_count,
                idempotency_key=command.idempotency_key,
                replayed=True,
            )

        await self._publish_or_mark_failed(
            command=command,
            job_id=job_result.job.job_id,
        )
        await self._mark_queued_or_raise(
            job_id=job_result.job.job_id,
            published_record_count=accepted_count,
        )
        return BusinessDateIngestionCommandResult(
            message="Business dates accepted for asynchronous ingestion processing.",
            job_id=job_result.job.job_id,
            accepted_count=accepted_count,
            idempotency_key=command.idempotency_key,
            replayed=False,
        )

    async def _assert_ingestion_writable(self) -> None:
        try:
            await self.ingestion_job_service.assert_ingestion_writable()
        except PermissionError as exc:
            raise BusinessDateIngestionCommandError(
                HTTP_SERVICE_UNAVAILABLE,
                {"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
            ) from exc

    @staticmethod
    def _enforce_rate_limit(record_count: int) -> None:
        try:
            enforce_ingestion_write_rate_limit(
                endpoint="/ingest/business-dates",
                record_count=record_count,
            )
        except PermissionError as exc:
            raise BusinessDateIngestionCommandError(
                HTTP_TOO_MANY_REQUESTS,
                {"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
            ) from exc

    async def _validate_request(self, request: BusinessDateIngestionRequest) -> None:
        try:
            await self.business_date_policy.validate(request)
        except BusinessDatePolicyViolation as exc:
            raise BusinessDateIngestionCommandError(
                HTTP_UNPROCESSABLE_CONTENT,
                {"code": exc.code, "message": exc.message},
            ) from exc

    async def _create_ingestion_job(
        self,
        *,
        command: BusinessDateIngestionCommand,
        accepted_count: int,
    ):
        correlation_id, request_id, trace_id = get_request_lineage()
        return await self.ingestion_job_service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            endpoint=command.endpoint,
            entity_type="business_date",
            accepted_count=accepted_count,
            idempotency_key=command.idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=command.request.model_dump(mode="json"),
        )

    async def _publish_or_mark_failed(
        self,
        *,
        command: BusinessDateIngestionCommand,
        job_id: str,
    ) -> None:
        try:
            await self.ingestion_service.publish_business_dates(
                command.request.business_dates,
                idempotency_key=command.idempotency_key,
            )
        except IngestionPublishError as exc:
            await self.ingestion_job_service.mark_failed(
                job_id,
                str(exc),
                failed_record_keys=exc.failed_record_keys,
            )
            raise BusinessDateIngestionPublishUnavailable(
                publish_error=exc,
                job_id=job_id,
            ) from exc
        except Exception as exc:
            await self.ingestion_job_service.mark_failed(job_id, str(exc))
            raise

    async def _mark_queued_or_raise(
        self,
        *,
        job_id: str,
        published_record_count: int,
    ) -> None:
        try:
            queued = await self.ingestion_job_service.mark_queued(job_id)
        except Exception as exc:
            await self._record_bookkeeping_failure(job_id=job_id, failure_reason=str(exc))
            raise BusinessDateBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
            ) from exc

        if not queued:
            await self._record_bookkeeping_failure(
                job_id=job_id,
                failure_reason="job queue transition was rejected",
            )
            raise BusinessDateBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
            )

    async def _record_bookkeeping_failure(self, *, job_id: str, failure_reason: str) -> None:
        try:
            await self.ingestion_job_service.record_failure_observation(
                job_id,
                failure_reason,
                failure_phase="queue_bookkeeping",
            )
        except Exception:
            logger.exception(
                "Failed to persist ingestion bookkeeping failure observation.",
                extra={"job_id": job_id, "failure_phase": "queue_bookkeeping"},
            )
