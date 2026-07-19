from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from portfolio_common.domain.valuation.assignments import ValuationPolicyAssignmentError

from ..application.reference_data_ingestion_registry import (
    ReferenceDataIngestionCommand as ReferenceDataRegistryCommand,
)
from ..application.reference_data_ingestion_registry import (
    ReferenceDataPayload,
)
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import create_ingestion_job_id, get_request_lineage
from .ingestion_job_service import IngestionJobService
from .reference_data_ingestion_service import ReferenceDataIngestionService

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_CONFLICT = 409
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_INTERNAL_SERVER_ERROR = 500


class ReferenceDataIngestionCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "command failed"))))
        self.status_code = status_code
        self.detail = detail


class ReferenceDataBookkeepingFailed(Exception):
    def __init__(self, *, job_id: str) -> None:
        super().__init__("Reference-data ingestion bookkeeping failed after persistence.")
        self.job_id = job_id
        self.failure_phase = "persist_bookkeeping"
        self.publish_state = "not_published"
        self.work_state = "persisted"
        self.published_record_count = 0


@dataclass(frozen=True, slots=True)
class ReferenceDataIngestionCommand:
    endpoint: str
    idempotency_key: str | None
    registry_command: ReferenceDataRegistryCommand
    request: ReferenceDataPayload


@dataclass(frozen=True, slots=True)
class ReferenceDataIngestionCommandResult:
    message: str
    entity_type: str
    job_id: str
    accepted_count: int
    idempotency_key: str | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class ReferenceDataIngestionCommandHandler:
    reference_data_service: ReferenceDataIngestionService
    ingestion_job_service: IngestionJobService

    async def ingest_reference_data(
        self,
        command: ReferenceDataIngestionCommand,
    ) -> ReferenceDataIngestionCommandResult:
        await self._assert_ingestion_writable()
        accepted_count = command.registry_command.accepted_count(command.request)
        self._enforce_rate_limit(command.registry_command.endpoint, accepted_count)
        job_result = await self._create_job(command=command, accepted_count=accepted_count)
        entity_type = command.registry_command.entity_type
        if not job_result.created:
            return ReferenceDataIngestionCommandResult(
                message="Duplicate ingestion request accepted via idempotency replay.",
                entity_type=entity_type,
                job_id=job_result.job.job_id,
                accepted_count=job_result.job.accepted_count,
                idempotency_key=command.idempotency_key,
                replayed=True,
            )

        await self._persist_or_mark_failed(command, job_result.job.job_id)
        await self._mark_queued_or_raise(job_id=job_result.job.job_id)
        return ReferenceDataIngestionCommandResult(
            message=f"{entity_type} accepted for asynchronous ingestion processing.",
            entity_type=entity_type,
            job_id=job_result.job.job_id,
            accepted_count=accepted_count,
            idempotency_key=command.idempotency_key,
        )

    async def _assert_ingestion_writable(self) -> None:
        try:
            await self.ingestion_job_service.assert_ingestion_writable()
        except PermissionError as exc:
            raise ReferenceDataIngestionCommandError(
                HTTP_SERVICE_UNAVAILABLE,
                {"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
            ) from exc

    @staticmethod
    def _enforce_rate_limit(endpoint: str, record_count: int) -> None:
        try:
            enforce_ingestion_write_rate_limit(endpoint=endpoint, record_count=record_count)
        except PermissionError as exc:
            raise ReferenceDataIngestionCommandError(
                HTTP_TOO_MANY_REQUESTS,
                {"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
            ) from exc

    async def _create_job(
        self,
        *,
        command: ReferenceDataIngestionCommand,
        accepted_count: int,
    ):
        correlation_id, request_id, trace_id = get_request_lineage()
        return await self.ingestion_job_service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            endpoint=command.endpoint,
            entity_type=command.registry_command.entity_type,
            accepted_count=accepted_count,
            idempotency_key=command.idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=command.registry_command.request_payload(command.request),
        )

    async def _persist_or_mark_failed(
        self,
        command: ReferenceDataIngestionCommand,
        job_id: str,
    ) -> None:
        try:
            await command.registry_command.persist(self.reference_data_service, command.request)
        except ValuationPolicyAssignmentError as exc:
            await self.ingestion_job_service.mark_failed(job_id, str(exc), failure_phase="persist")
            raise ReferenceDataIngestionCommandError(
                HTTP_CONFLICT,
                {
                    "code": "VALUATION_POLICY_ASSIGNMENT_CONFLICT",
                    "message": str(exc),
                    "job_id": job_id,
                },
            ) from exc
        except Exception as exc:
            await self.ingestion_job_service.mark_failed(job_id, str(exc), failure_phase="persist")
            raise ReferenceDataIngestionCommandError(
                HTTP_INTERNAL_SERVER_ERROR,
                {
                    "code": "REFERENCE_DATA_PERSIST_FAILED",
                    "message": str(exc),
                    "job_id": job_id,
                },
            ) from exc

    async def _mark_queued_or_raise(self, *, job_id: str) -> None:
        try:
            queued = await self.ingestion_job_service.mark_queued(job_id)
        except Exception as exc:
            await self._record_bookkeeping_failure(job_id=job_id, failure_reason=str(exc))
            raise ReferenceDataBookkeepingFailed(job_id=job_id) from exc

        if not queued:
            await self._record_bookkeeping_failure(
                job_id=job_id,
                failure_reason="job queue transition was rejected",
            )
            raise ReferenceDataBookkeepingFailed(job_id=job_id)

    async def _record_bookkeeping_failure(self, *, job_id: str, failure_reason: str) -> None:
        try:
            await self.ingestion_job_service.record_failure_observation(
                job_id,
                failure_reason,
                failure_phase="persist_bookkeeping",
            )
        except Exception:
            logger.exception(
                "Failed to persist reference-data bookkeeping failure observation.",
                extra={"job_id": job_id, "failure_phase": "persist_bookkeeping"},
            )
