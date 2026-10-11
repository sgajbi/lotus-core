from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from portfolio_common.monitoring import (
    INGESTION_JOBS_CREATED_TOTAL,
    INGESTION_JOBS_FAILED_TOTAL,
    INGESTION_JOBS_RETRIED_TOTAL,
)
from portfolio_common.transaction_batch_lineage import transaction_batch_lineage_from_payload
from sqlalchemy import and_, desc, func, inspect, null, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.ingestion_failure_evidence import project_ingestion_failure_evidence
from ..domain.ingestion_job_lifecycle_policy import (
    INGESTION_JOB_TERMINAL_STATUSES,
    IngestionJobStatus,
    IngestionJobTransition,
    ingestion_job_transition_allowed,
    ingestion_job_transition_expected_statuses,
)
from ..DTOs.ingestion_job_dto import (
    IngestionJobFailureResponse,
    IngestionJobResponse,
)
from ..request_metadata import idempotency_key_reference
from .ingestion_payload_evidence import (
    build_ingestion_payload_evidence,
    ingestion_payload_fingerprint_matches,
)


class IngestionIdempotencyConflictError(ValueError):
    def __init__(self, *, endpoint: str, idempotency_key: str):
        self.endpoint = endpoint
        self.idempotency_key = idempotency_key
        super().__init__(
            "Ingestion idempotency key was reused for the same endpoint with a different payload."
        )


_SYNCHRONOUS_CREATION_ROW = "portfolio_source_observation_creation_row"
_SYNCHRONOUS_OBSERVATION_ENDPOINTS = frozenset(
    {
        "/ingest/portfolio-cash-availability-observations",
        "/ingest/portfolio-funding-investment-observations",
    }
)


async def complete_synchronous_observation_receipt(
    db: AsyncSession, row: DBIngestionJob, *, tenant_id: str, job_id: str
) -> None:
    """Finish only the new observation receipt inside its creation transaction.

    The dedicated callback invokes this after append/CAS has succeeded. It cannot
    complete an existing, foreign, detached or asynchronous job, nor commit facts.
    The surrounding creation transaction owns both completion and rollback.
    """
    if (
        not db.in_transaction()
        or db.info.get(_SYNCHRONOUS_CREATION_ROW) is not row
        or inspect(row).session is not db.sync_session
        or not inspect(row).persistent
        or row.tenant_id != tenant_id
        or row.job_id != job_id
        or row.endpoint not in _SYNCHRONOUS_OBSERVATION_ENDPOINTS
        or not ingestion_job_transition_allowed(
            transition=IngestionJobTransition.ACCEPTED_TO_COMPLETED,
            current_status=row.status,
        )
    ):
        raise ValueError("Synchronous observation receipt is not an attached creation effect")
    row.status = IngestionJobStatus.COMPLETED.value
    row.completed_at = datetime.now(UTC)
    await db.flush()


@dataclass(slots=True)
class IngestionJobReplayContext:
    job_id: str
    tenant_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    request_payload: dict[str, Any] | None
    request_payload_policy_version: str
    request_payload_representation: str
    request_payload_replay_eligible: bool
    request_payload_partial_replay_eligible: bool
    request_payload_replay_expires_at: datetime | None
    request_payload_retention_authority: str
    submitted_at: datetime
    transaction_batch_lineage: dict[str, Any] | None = None


@dataclass(slots=True)
class IngestionJobCreateResult:
    job: IngestionJobResponse
    created: bool


def to_job_response(
    job: DBIngestionJob,
    *,
    reference_key_id: str,
    reference_hmac_secret: str,
    include_raw_idempotency_key: bool,
) -> IngestionJobResponse:
    raw_idempotency_key = job.idempotency_key
    return IngestionJobResponse(
        job_id=job.job_id,
        tenant_id=job.tenant_id,
        endpoint=job.endpoint,
        entity_type=job.entity_type,
        status=job.status,  # type: ignore[arg-type]
        accepted_count=job.accepted_count,
        idempotency_key=raw_idempotency_key if include_raw_idempotency_key else None,
        idempotency_key_reference=(
            idempotency_key_reference(
                value=raw_idempotency_key,
                key_id=reference_key_id,
                hmac_secret=reference_hmac_secret,
            )
            if raw_idempotency_key is not None
            else None
        ),
        request_payload_fingerprint=getattr(job, "request_payload_fingerprint", None),
        request_payload_policy_version=getattr(job, "request_payload_policy_version", None),
        request_payload_classification=getattr(job, "request_payload_classification", None),
        request_payload_representation=getattr(job, "request_payload_representation", None),
        request_payload_replay_eligible=getattr(job, "request_payload_replay_eligible", None),
        request_payload_partial_replay_eligible=getattr(
            job, "request_payload_partial_replay_eligible", None
        ),
        request_payload_replay_expires_at=getattr(job, "request_payload_replay_expires_at", None),
        request_payload_retention_authority=getattr(
            job, "request_payload_retention_authority", None
        ),
        correlation_id=job.correlation_id,
        request_id=job.request_id,
        trace_id=job.trace_id,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        failure_reason=job.failure_reason,
        failure_status_code=job.failure_status_code,
        failure_code=job.failure_code,
        failure_detail=job.failure_detail,
        failure_headers=job.failure_headers,
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
    tenant_id: str,
    endpoint: str,
    entity_type: str,
    accepted_count: int,
    idempotency_key: str | None,
    correlation_id: str,
    request_id: str,
    trace_id: str,
    request_payload: dict[str, Any] | None,
    fingerprint_key_id: str,
    fingerprint_hmac_secret: str,
    fingerprint_previous_keys: Mapping[str, str],
    session_factory,
    on_created: Callable[[AsyncSession, DBIngestionJob], Awaitable[None]] | None = None,
) -> IngestionJobCreateResult:
    if request_payload is None:
        raise ValueError("Ingestion jobs require request payload evidence.")
    payload_evidence = build_ingestion_payload_evidence(
        endpoint=endpoint,
        entity_type=entity_type,
        payload=request_payload,
        observed_at=datetime.now(UTC),
        fingerprint_key_id=fingerprint_key_id,
        fingerprint_hmac_secret=fingerprint_hmac_secret,
    )
    fingerprint_keyring = {
        **fingerprint_previous_keys,
        fingerprint_key_id: fingerprint_hmac_secret,
    }
    async for db in session_factory():
        async with db.begin():
            if idempotency_key:
                await _acquire_idempotency_key_lock(
                    db,
                    tenant_id=tenant_id,
                    endpoint=endpoint,
                    idempotency_key=idempotency_key,
                )
                existing = await db.scalar(
                    select(DBIngestionJob)
                    .where(
                        and_(
                            DBIngestionJob.tenant_id == tenant_id,
                            DBIngestionJob.endpoint == endpoint,
                            DBIngestionJob.idempotency_key == idempotency_key,
                        )
                    )
                    .order_by(desc(DBIngestionJob.submitted_at))
                    .limit(1)
                )
                if existing is not None:
                    if _idempotency_payload_conflicts(
                        existing_payload_fingerprint=getattr(
                            existing,
                            "request_payload_fingerprint",
                            None,
                        ),
                        requested_payload=request_payload,
                        fingerprint_keyring=fingerprint_keyring,
                    ):
                        raise IngestionIdempotencyConflictError(
                            endpoint=endpoint,
                            idempotency_key=idempotency_key,
                        )
                    return IngestionJobCreateResult(
                        job=to_job_response(
                            existing,
                            reference_key_id=fingerprint_key_id,
                            reference_hmac_secret=fingerprint_hmac_secret,
                            include_raw_idempotency_key=True,
                        ),
                        created=False,
                    )

            row = DBIngestionJob(
                job_id=job_id,
                tenant_id=tenant_id,
                endpoint=endpoint,
                entity_type=entity_type,
                status=IngestionJobStatus.ACCEPTED.value,
                accepted_count=accepted_count,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
                request_payload=payload_evidence.request_payload,
                transaction_batch_lineage=(
                    transaction_batch_lineage_from_payload(request_payload or {}).model_dump()
                    if endpoint
                    in {
                        "/ingest/transactions",
                        "/ingest/portfolio-bundle",
                        "/reprocess/transactions",
                    }
                    else None
                ),
                request_payload_fingerprint=payload_evidence.request_payload_fingerprint,
                request_payload_policy_version=payload_evidence.policy_version,
                request_payload_classification=payload_evidence.classification,
                request_payload_representation=payload_evidence.durable_representation,
                request_payload_replay_eligible=payload_evidence.replay_eligible,
                request_payload_partial_replay_eligible=(payload_evidence.partial_replay_eligible),
                request_payload_replay_expires_at=payload_evidence.replay_expires_at,
                request_payload_retention_authority=payload_evidence.retention_authority,
            )
            db.add(row)
            await db.flush()
            if on_created is not None:
                # Capability-specific durable intent shares this existing job UOW.
                # Exact idempotent returns above never repeat the creation effect.
                if endpoint not in _SYNCHRONOUS_OBSERVATION_ENDPOINTS:
                    await on_created(db, row)
                else:
                    db.info[_SYNCHRONOUS_CREATION_ROW] = row
                    try:
                        await on_created(db, row)
                    finally:
                        db.info.pop(_SYNCHRONOUS_CREATION_ROW, None)
            INGESTION_JOBS_CREATED_TOTAL.labels(endpoint=endpoint, entity_type=entity_type).inc()
            return IngestionJobCreateResult(
                job=to_job_response(
                    row,
                    reference_key_id=fingerprint_key_id,
                    reference_hmac_secret=fingerprint_hmac_secret,
                    include_raw_idempotency_key=True,
                ),
                created=True,
            )

    msg = "Unable to create ingestion job due to unavailable database session."
    raise RuntimeError(msg)


async def _acquire_idempotency_key_lock(
    db,
    *,
    tenant_id: str,
    endpoint: str,
    idempotency_key: str,
) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{tenant_id}|{endpoint}|{idempotency_key}"},
    )


async def mark_job_queued(
    *,
    job_id: str,
    tenant_id: str,
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
                .where(DBIngestionJob.tenant_id == tenant_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .where(DBIngestionJob.status.not_in(tuple(INGESTION_JOB_TERMINAL_STATUSES)))
                .values(
                    status=IngestionJobStatus.QUEUED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=None,
                    failure_status_code=None,
                    failure_code=None,
                    failure_detail=null(),
                    failure_headers=null(),
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
    failure_status_code: int | None = None,
    failure_code: str | None = None,
    failure_detail: dict[str, Any] | None = None,
    failure_headers: dict[str, str] | None = None,
    tenant_id: str,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.MARK_FAILED
    )
    async for db in session_factory():
        async with db.begin():
            failure_outcome_values = _failure_outcome_values(
                failure_status_code=failure_status_code,
                failure_code=failure_code,
                failure_detail=failure_detail,
                failure_headers=failure_headers,
            )
            evidence = project_ingestion_failure_evidence(
                failure_code=failure_code,
                failure_detail=failure_detail,
                failure_headers=failure_headers,
            )
            if failure_outcome_values:
                failure_outcome_values["failure_detail"] = evidence.detail
                failure_outcome_values["failure_headers"] = evidence.headers
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.tenant_id == tenant_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .where(DBIngestionJob.status.not_in(tuple(INGESTION_JOB_TERMINAL_STATUSES)))
                .values(
                    status=IngestionJobStatus.FAILED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=evidence.reason,
                    **failure_outcome_values,
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
                    failure_reason=evidence.reason,
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
    failure_status_code: int | None = None,
    failure_code: str | None = None,
    failure_detail: dict[str, Any] | None = None,
    failure_headers: dict[str, str] | None = None,
) -> None:
    async for db in session_factory():
        async with db.begin():
            row = await db.scalar(
                select(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.status.not_in(tuple(INGESTION_JOB_TERMINAL_STATUSES)))
                .limit(1)
            )
            if row is None:
                return
            failure_outcome_values = _failure_outcome_values(
                failure_status_code=failure_status_code,
                failure_code=failure_code,
                failure_detail=failure_detail,
                failure_headers=failure_headers,
            )
            evidence = project_ingestion_failure_evidence(
                failure_code=failure_code,
                failure_detail=failure_detail,
                failure_headers=failure_headers,
            )
            if failure_outcome_values:
                failure_outcome_values["failure_detail"] = evidence.detail
                failure_outcome_values["failure_headers"] = evidence.headers
            for field_name, value in failure_outcome_values.items():
                setattr(row, field_name, value)
            db.add(
                _build_failure_row(
                    job_id=job_id,
                    failure_phase=failure_phase,
                    failure_reason=evidence.reason,
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
    tenant_id: str,
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
                .where(DBIngestionJob.tenant_id == tenant_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .where(DBIngestionJob.status.not_in(tuple(INGESTION_JOB_TERMINAL_STATUSES)))
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
    tenant_id: str,
) -> bool:
    expected_statuses = expected_statuses or ingestion_job_transition_expected_statuses(
        IngestionJobTransition.RETRY_TO_QUEUED
    )
    async for db in session_factory():
        async with db.begin():
            updated = await db.execute(
                update(DBIngestionJob)
                .where(DBIngestionJob.job_id == job_id)
                .where(DBIngestionJob.tenant_id == tenant_id)
                .where(DBIngestionJob.status.in_(tuple(expected_statuses)))
                .where(DBIngestionJob.status.not_in(tuple(INGESTION_JOB_TERMINAL_STATUSES)))
                .values(
                    status=IngestionJobStatus.QUEUED.value,
                    completed_at=datetime.now(UTC),
                    failure_reason=None,
                    failure_status_code=None,
                    failure_code=None,
                    failure_detail=null(),
                    failure_headers=null(),
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
    reference_key_id: str,
    reference_hmac_secret: str,
    tenant_id: str,
) -> IngestionJobResponse | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBIngestionJob)
            .where(DBIngestionJob.job_id == job_id)
            .where(DBIngestionJob.tenant_id == tenant_id)
            .limit(1)
        )
        return (
            to_job_response(
                row,
                reference_key_id=reference_key_id,
                reference_hmac_secret=reference_hmac_secret,
                include_raw_idempotency_key=False,
            )
            if row
            else None
        )
    return None


async def get_job_replay_context_response(
    *,
    job_id: str,
    session_factory,
    tenant_id: str,
) -> IngestionJobReplayContext | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBIngestionJob)
            .where(DBIngestionJob.job_id == job_id)
            .where(DBIngestionJob.tenant_id == tenant_id)
            .limit(1)
        )
        if row is None:
            return None
        payload = row.request_payload if isinstance(row.request_payload, dict) else None
        return IngestionJobReplayContext(
            job_id=row.job_id,
            tenant_id=row.tenant_id,
            endpoint=row.endpoint,
            entity_type=row.entity_type,
            accepted_count=row.accepted_count,
            idempotency_key=row.idempotency_key,
            request_payload=payload,
            transaction_batch_lineage=row.transaction_batch_lineage,
            request_payload_policy_version=row.request_payload_policy_version,
            request_payload_representation=row.request_payload_representation,
            request_payload_replay_eligible=row.request_payload_replay_eligible,
            request_payload_partial_replay_eligible=(row.request_payload_partial_replay_eligible),
            request_payload_replay_expires_at=row.request_payload_replay_expires_at,
            request_payload_retention_authority=row.request_payload_retention_authority,
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


def _failure_outcome_values(
    *,
    failure_status_code: int | None,
    failure_code: str | None,
    failure_detail: dict[str, Any] | None,
    failure_headers: dict[str, str] | None,
) -> dict[str, Any]:
    if failure_status_code is None and failure_code is None:
        if failure_detail is not None or failure_headers is not None:
            raise ValueError(
                "Failure detail or headers require both a failure status code and error code."
            )
        return {}
    if failure_status_code is None or failure_code is None:
        raise ValueError("Failure status code and error code must be recorded together.")
    if failure_status_code < 400 or failure_status_code > 599:
        raise ValueError("Failure status code must be between 400 and 599.")
    normalized_code = failure_code.strip()
    if not normalized_code:
        raise ValueError("Failure error code must be non-empty.")
    return {
        "failure_status_code": failure_status_code,
        "failure_code": normalized_code,
        "failure_detail": dict(failure_detail) if failure_detail is not None else None,
        "failure_headers": dict(failure_headers) if failure_headers is not None else None,
    }


def _idempotency_payload_conflicts(
    *,
    existing_payload_fingerprint: str | None,
    requested_payload: dict[str, Any] | None,
    fingerprint_keyring: Mapping[str, str],
) -> bool:
    if existing_payload_fingerprint is not None:
        return not ingestion_payload_fingerprint_matches(
            stored_fingerprint=existing_payload_fingerprint,
            payload=requested_payload,
            secrets_by_key_id=fingerprint_keyring,
        )
    # A legacy row without the full original request fingerprint cannot prove
    # payload identity. Redacted bodies are deliberately insufficient because
    # two requests that differ only in a sensitive value would otherwise alias.
    return True
