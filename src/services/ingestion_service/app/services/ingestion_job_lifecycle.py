from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from portfolio_common.monitoring import (
    INGESTION_JOBS_CREATED_TOTAL,
    INGESTION_JOBS_FAILED_TOTAL,
    INGESTION_JOBS_RETRIED_TOTAL,
)
from sqlalchemy import and_, desc, func, select, text, update

from ..domain.ingestion_job_lifecycle_policy import (
    IngestionJobStatus,
    IngestionJobTransition,
    ingestion_job_transition_expected_statuses,
)
from ..DTOs.ingestion_job_dto import (
    IngestionJobFailureResponse,
    IngestionJobResponse,
)
from .ingestion_payload_evidence import (
    ingestion_payload_fingerprint,
    source_safe_payload_fingerprint,
    source_safe_request_payload,
)


class IngestionIdempotencyConflictError(ValueError):
    def __init__(self, *, endpoint: str, idempotency_key: str):
        self.endpoint = endpoint
        self.idempotency_key = idempotency_key
        super().__init__(
            "Ingestion idempotency key was reused for the same endpoint with a different payload."
        )


@dataclass(slots=True)
class IngestionJobReplayContext:
    job_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    request_payload: dict[str, Any] | None
    submitted_at: datetime


@dataclass(slots=True)
class IngestionJobCreateResult:
    job: IngestionJobResponse
    created: bool


def to_job_response(job: DBIngestionJob) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job.job_id,
        endpoint=job.endpoint,
        entity_type=job.entity_type,
        status=job.status,  # type: ignore[arg-type]
        accepted_count=job.accepted_count,
        idempotency_key=job.idempotency_key,
        correlation_id=job.correlation_id,
        request_id=job.request_id,
        trace_id=job.trace_id,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        failure_reason=job.failure_reason,
        retry_count=job.retry_count,
        last_retried_at=job.last_retried_at,
    )


def to_failure_response(failure: DBIngestionJobFailure) -> IngestionJobFailureResponse:
    return IngestionJobFailureResponse(
        failure_id=failure.failure_id,
        job_id=failure.job_id,
        failure_phase=failure.failure_phase,
        failure_reason=failure.failure_reason,
        failed_record_keys=list(failure.failed_record_keys or []),
        failed_at=failure.failed_at,
    )


async def create_or_get_job_result(
    *,
    job_id: str,
    endpoint: str,
    entity_type: str,
    accepted_count: int,
    idempotency_key: str | None,
    correlation_id: str,
    request_id: str,
    trace_id: str,
    request_payload: dict[str, Any] | None,
    session_factory,
) -> IngestionJobCreateResult:
    async for db in session_factory():
        async with db.begin():
            if idempotency_key:
                await _acquire_idempotency_key_lock(
                    db,
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                )
                existing = await db.scalar(
                    select(DBIngestionJob)
                    .where(
                        and_(
                            DBIngestionJob.endpoint == endpoint,
                            DBIngestionJob.idempotency_key == idempotency_key,
                        )
                    )
                    .order_by(desc(DBIngestionJob.submitted_at))
                    .limit(1)
                )
                if existing is not None:
                    if _idempotency_payload_conflicts(
                        existing_payload=existing.request_payload,
                        existing_payload_fingerprint=getattr(
                            existing,
                            "request_payload_fingerprint",
                            None,
                        ),
                        requested_payload=request_payload,
                    ):
                        raise IngestionIdempotencyConflictError(
                            endpoint=endpoint,
                            idempotency_key=idempotency_key,
                        )
                    return IngestionJobCreateResult(job=to_job_response(existing), created=False)

            row = DBIngestionJob(
                job_id=job_id,
                endpoint=endpoint,
                entity_type=entity_type,
                status=IngestionJobStatus.ACCEPTED.value,
                accepted_count=accepted_count,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
                request_payload=cast(
                    dict[str, Any] | None,
                    source_safe_request_payload(request_payload),
                ),
                request_payload_fingerprint=ingestion_payload_fingerprint(request_payload),
            )
            db.add(row)
            await db.flush()
            INGESTION_JOBS_CREATED_TOTAL.labels(endpoint=endpoint, entity_type=entity_type).inc()
            return IngestionJobCreateResult(job=to_job_response(row), created=True)

    msg = "Unable to create ingestion job due to unavailable database session."
    raise RuntimeError(msg)


async def _acquire_idempotency_key_lock(db, *, endpoint: str, idempotency_key: str) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{endpoint}|{idempotency_key}"},
    )


async def mark_job_queued(
    *,
    job_id: str,
    session_factory,
    expected_statuses: Sequence[str] | None = None,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.ACCEPTED_TO_QUEUED
    )
    async for db in session_factory():
        async with db.begin():
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .values(
                    status=IngestionJobStatus.QUEUED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=None,
                )
                .returning(DBIngestionJob.status)
            )
            return updated.first() is not None
    return False


async def mark_job_failed(
    *,
    job_id: str,
    failure_reason: str,
    failure_phase: str,
    failed_record_keys: list[str] | None,
    session_factory,
    expected_statuses: Sequence[str] | None = None,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.MARK_FAILED
    )
    async for db in session_factory():
        async with db.begin():
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .values(
                    status=IngestionJobStatus.FAILED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=failure_reason,
                )
                .returning(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
            )
            row = updated.first()
            if row is None:
                return False
            db.add(
                _build_failure_row(
                    job_id=job_id,
                    failure_phase=failure_phase,
                    failure_reason=failure_reason,
                    failed_record_keys=failed_record_keys,
                )
            )
            INGESTION_JOBS_FAILED_TOTAL.labels(
                endpoint=row.endpoint,
                entity_type=row.entity_type,
                failure_phase=failure_phase,
            ).inc()
            return True
    return False


async def record_job_failure_observation(
    *,
    job_id: str,
    failure_reason: str,
    failure_phase: str,
    failed_record_keys: list[str] | None,
    session_factory,
) -> None:
    async for db in session_factory():
        async with db.begin():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            if row is None:
                return
            db.add(
                _build_failure_row(
                    job_id=job_id,
                    failure_phase=failure_phase,
                    failure_reason=failure_reason,
                    failed_record_keys=failed_record_keys,
                )
            )
            INGESTION_JOBS_FAILED_TOTAL.labels(
                endpoint=row.endpoint,
                entity_type=row.entity_type,
                failure_phase=failure_phase,
            ).inc()


async def mark_job_retried(
    *,
    job_id: str,
    session_factory,
    expected_statuses: Sequence[str] | None = None,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.MARK_RETRIED
    )
    async for db in session_factory():
        async with db.begin():
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .values(
                    retry_count=func.coalesce(DBIngestionJob.retry_count, 0) + 1,
                    last_retried_at=datetime.now(UTC),
                )
                .returning(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
            )
            row = updated.first()
            if row is None:
                return False
            INGESTION_JOBS_RETRIED_TOTAL.labels(
                endpoint=row.endpoint, entity_type=row.entity_type, result="accepted"
            ).inc()
            return True
    return False


async def mark_job_retried_and_queued(
    *,
    job_id: str,
    session_factory,
    expected_statuses: Sequence[str] | None = None,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.RETRY_TO_QUEUED
    )
    async for db in session_factory():
        async with db.begin():
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .values(
                    status=IngestionJobStatus.QUEUED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=None,
                    retry_count=func.coalesce(DBIngestionJob.retry_count, 0) + 1,
                    last_retried_at=datetime.now(UTC),
                )
                .returning(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
            )
            row = updated.first()
            if row is None:
                return False
            INGESTION_JOBS_RETRIED_TOTAL.labels(
                endpoint=row.endpoint, entity_type=row.entity_type, result="accepted"
            ).inc()
            return True
    return False


async def get_job_response(
    *,
    job_id: str,
    session_factory,
) -> IngestionJobResponse | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
        )
        return to_job_response(row) if row else None
    return None


async def get_job_replay_context_response(
    *,
    job_id: str,
    session_factory,
) -> IngestionJobReplayContext | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
        )
        if row is None:
            return None
        payload = row.request_payload if isinstance(row.request_payload, dict) else None
        return IngestionJobReplayContext(
            job_id=row.job_id,
            endpoint=row.endpoint,
            entity_type=row.entity_type,
            accepted_count=row.accepted_count,
            idempotency_key=row.idempotency_key,
            request_payload=payload,
            submitted_at=row.submitted_at,
        )
    return None


async def list_failure_responses(
    *,
    job_id: str,
    limit: int,
    session_factory,
) -> list[IngestionJobFailureResponse]:
    async for db in session_factory():
        rows = (
            await db.scalars(
                select(DBIngestionJobFailure)
                .where(DBIngestionJobFailure.job_id == job_id)
                .order_by(desc(DBIngestionJobFailure.failed_at))
                .limit(limit)
            )
        ).all()
        return [to_failure_response(row) for row in rows]
    return []


def _build_failure_row(
    *,
    job_id: str,
    failure_phase: str,
    failure_reason: str,
    failed_record_keys: list[str] | None,
) -> DBIngestionJobFailure:
    return DBIngestionJobFailure(
        failure_id=f"fail_{uuid4().hex}",
        job_id=job_id,
        failure_phase=failure_phase,
        failure_reason=failure_reason,
        failed_record_keys=failed_record_keys or [],
    )


def _idempotency_payload_conflicts(
    *,
    existing_payload: Any,
    existing_payload_fingerprint: str | None,
    requested_payload: dict[str, Any] | None,
) -> bool:
    requested_payload_fingerprint = ingestion_payload_fingerprint(requested_payload)
    if existing_payload_fingerprint is not None:
        return existing_payload_fingerprint != requested_payload_fingerprint
    existing_payload_dict = existing_payload if isinstance(existing_payload, dict) else None
    return source_safe_payload_fingerprint(
        existing_payload_dict
    ) != source_safe_payload_fingerprint(requested_payload)
