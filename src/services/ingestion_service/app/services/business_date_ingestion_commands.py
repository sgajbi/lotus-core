from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from portfolio_common.domain.tenant import TenantContext
from portfolio_common.ingestion_lineage import ingestion_job_scope

from ..application.ingestion_bookkeeping_outcome import (
    INGESTION_JOB_BOOKKEEPING_FAILED_CODE,
    build_ingestion_bookkeeping_failure_detail,
)
from ..application.ingestion_idempotency_replay import (
    resolve_ingestion_idempotency_replay,
)
from ..application.ingestion_publish_outcome import (
    INGESTION_PUBLISH_FAILED_CODE,
    INGESTION_PUBLISH_RETRY_AFTER_SECONDS,
    build_ingestion_publish_failure_detail,
)
from ..DTOs.business_date_dto import BusinessDateIngestionRequest
from ..DTOs.ingestion_job_dto import IngestionJobResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..ports.ingestion_idempotency_replay import (
    IngestionIdempotencyReplay,
    IngestionIdempotencyReplayReader,
)
from ..request_metadata import create_ingestion_job_id, get_request_lineage
from .business_date_ingestion_policy import (
    BusinessDateIngestionPolicy,
    BusinessDatePolicyViolation,
)
from .ingestion_job_lifecycle import IngestionJobCreateResult
from .ingestion_job_service import IngestionJobService
from .ingestion_service import IngestionPublishError, IngestionService

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_SERVICE_UNAVAILABLE = 503


class BusinessDateIngestionCommandError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "command failed"))))
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class BusinessDateIngestionPublishUnavailable(Exception):
    def __init__(self, *, publish_error: IngestionPublishError, job_id: str) -> None:
        super().__init__(str(publish_error))
        self.publish_error = publish_error
        self.job_id = job_id


class BusinessDateBookkeepingFailed(Exception):
    def __init__(
        self,
        *,
        job_id: str,
        published_record_count: int,
        detail: dict[str, object],
    ) -> None:
        super().__init__("Business-date ingestion bookkeeping failed after publish.")
        self.job_id = job_id
        self.published_record_count = published_record_count
        self.detail = detail
        self.failure_phase = "queue_bookkeeping"
        self.publish_state = "published"
        self.work_state = "published"


@dataclass(frozen=True, slots=True)
class BusinessDateIngestionCommand:
    tenant_context: TenantContext
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
    idempotency_replay_reader: IngestionIdempotencyReplayReader

    async def ingest_business_dates(
        self,
        command: BusinessDateIngestionCommand,
    ) -> BusinessDateIngestionCommandResult:
        accepted_count = len(command.request.business_dates)
        replay_job = await self.idempotency_replay_reader.find_matching_job(
            endpoint=command.endpoint,
            idempotency_key=command.idempotency_key,
            request_payload=command.request.model_dump(mode="json"),
        )
        if replay_job is not None:
            return self._replay_result(command, replay_job)

        await self._assert_ingestion_writable()
        self._enforce_rate_limit(len(command.request.business_dates))
        await self._validate_request(command.request)

        job_result = await self._create_ingestion_job(
            command=command,
            accepted_count=accepted_count,
        )
        if not job_result.created:
            return self._replay_result(command, job_result.job)

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

    @staticmethod
    def _replay_result(
        command: BusinessDateIngestionCommand,
        job: IngestionIdempotencyReplay | IngestionJobResponse,
    ) -> BusinessDateIngestionCommandResult:
        replay = resolve_ingestion_idempotency_replay(job)
        if not replay.accepted:
            raise BusinessDateIngestionCommandError(
                replay.status_code or 500,
                replay.detail
                or {
                    "code": "INGESTION_REPLAY_STATE_INVALID",
                    "message": "The stored ingestion replay outcome is incomplete.",
                    "job_id": job.job_id,
                },
                headers=replay.headers,
            )
        return BusinessDateIngestionCommandResult(
            message="Duplicate ingestion request accepted via idempotency replay.",
            job_id=job.job_id,
            accepted_count=job.accepted_count,
            idempotency_key=command.idempotency_key,
            replayed=True,
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
    ) -> IngestionJobCreateResult:
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
            tenant_context=command.tenant_context,
            request_payload=command.request.model_dump(mode="json"),
        )

    async def _publish_or_mark_failed(
        self,
        *,
        command: BusinessDateIngestionCommand,
        job_id: str,
    ) -> None:
        try:
            with ingestion_job_scope(job_id):
                await self.ingestion_service.publish_business_dates(
                    command.request.business_dates,
                    idempotency_key=command.idempotency_key,
                )
        except IngestionPublishError as exc:
            correlation_id, request_id, trace_id = get_request_lineage()
            detail = build_ingestion_publish_failure_detail(
                message=str(exc),
                failed_record_keys=exc.failed_record_keys,
                published_record_count=exc.published_record_count,
                job_id=job_id,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
            )
            await self.ingestion_job_service.mark_failed(
                job_id,
                str(detail["message"]),
                failed_record_keys=exc.failed_record_keys,
                failure_status_code=HTTP_SERVICE_UNAVAILABLE,
                failure_code=INGESTION_PUBLISH_FAILED_CODE,
                failure_detail=detail,
                failure_headers={"Retry-After": str(INGESTION_PUBLISH_RETRY_AFTER_SECONDS)},
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
            detail = await self._record_bookkeeping_failure(
                job_id=job_id,
                failure_reason=str(exc),
                published_record_count=published_record_count,
            )
            raise BusinessDateBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
                detail=detail,
            ) from exc

        if not queued:
            detail = await self._record_bookkeeping_failure(
                job_id=job_id,
                failure_reason="job queue transition was rejected",
                published_record_count=published_record_count,
            )
            raise BusinessDateBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
                detail=detail,
            )

    async def _record_bookkeeping_failure(
        self,
        *,
        job_id: str,
        failure_reason: str,
        published_record_count: int,
    ) -> dict[str, object]:
        correlation_id, request_id, trace_id = get_request_lineage()
        detail: dict[str, object] = build_ingestion_bookkeeping_failure_detail(
            job_id=job_id,
            failure_phase="queue_bookkeeping",
            publish_state="published",
            work_state="published",
            published_record_count=published_record_count,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
        )
        try:
            await self.ingestion_job_service.record_failure_observation(
                job_id,
                failure_reason,
                failure_phase="queue_bookkeeping",
                failure_status_code=500,
                failure_code=INGESTION_JOB_BOOKKEEPING_FAILED_CODE,
                failure_detail=detail,
            )
        except Exception:
            logger.exception(
                "Failed to persist ingestion bookkeeping failure observation.",
                extra={"job_id": job_id, "failure_phase": "queue_bookkeeping"},
            )
        return detail
