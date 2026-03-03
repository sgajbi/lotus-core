from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from typing import Any
from uuid import uuid4

from app.DTOs.ingestion_job_dto import (
    IngestionBacklogBreakdownItemResponse,
    IngestionBacklogBreakdownResponse,
    ConsumerDlqEventResponse,
    IngestionReplayAuditResponse,
    IngestionConsumerLagGroupResponse,
    IngestionConsumerLagResponse,
    IngestionErrorBudgetStatusResponse,
    IngestionHealthSummaryResponse,
    IngestionIdempotencyDiagnosticItemResponse,
    IngestionIdempotencyDiagnosticsResponse,
    IngestionJobFailureResponse,
    IngestionJobRecordStatusResponse,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionOpsModeResponse,
    IngestionSloStatusResponse,
    IngestionStalledJobListResponse,
    IngestionStalledJobResponse,
)
from portfolio_common.database_models import ConsumerDlqEvent as DBConsumerDlqEvent
from portfolio_common.database_models import ConsumerDlqReplayAudit as DBConsumerDlqReplayAudit
from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from portfolio_common.database_models import IngestionOpsControl as DBIngestionOpsControl
from portfolio_common.db import get_async_db_session
from portfolio_common.monitoring import (
    INGESTION_BACKLOG_AGE_SECONDS,
    INGESTION_JOBS_CREATED_TOTAL,
    INGESTION_JOBS_FAILED_TOTAL,
    INGESTION_JOBS_RETRIED_TOTAL,
    INGESTION_MODE_STATE,
    INGESTION_REPLAY_AUDIT_TOTAL,
    INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL,
    INGESTION_REPLAY_FAILURE_TOTAL,
)
from sqlalchemy import and_, case, desc, func, select

REPLAY_MAX_RECORDS_PER_REQUEST = int(
    os.getenv("LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST", "5000")
)
REPLAY_MAX_BACKLOG_JOBS = int(os.getenv("LOTUS_CORE_REPLAY_MAX_BACKLOG_JOBS", "5000"))


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


def _to_response(job: DBIngestionJob) -> IngestionJobResponse:
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


def _to_failure_response(failure: DBIngestionJobFailure) -> IngestionJobFailureResponse:
    return IngestionJobFailureResponse(
        failure_id=failure.failure_id,
        job_id=failure.job_id,
        failure_phase=failure.failure_phase,
        failure_reason=failure.failure_reason,
        failed_record_keys=list(failure.failed_record_keys or []),
        failed_at=failure.failed_at,
    )


def _to_dlq_event_response(event: DBConsumerDlqEvent) -> ConsumerDlqEventResponse:
    return ConsumerDlqEventResponse(
        event_id=event.event_id,
        original_topic=event.original_topic,
        consumer_group=event.consumer_group,
        dlq_topic=event.dlq_topic,
        original_key=event.original_key,
        error_reason_code=event.error_reason_code,
        error_reason=event.error_reason,
        correlation_id=event.correlation_id,
        payload_excerpt=event.payload_excerpt,
        observed_at=event.observed_at,
    )


def _to_replay_audit_response(row: DBConsumerDlqReplayAudit) -> IngestionReplayAuditResponse:
    return IngestionReplayAuditResponse(
        replay_id=row.replay_id,
        recovery_path=row.recovery_path,  # type: ignore[arg-type]
        event_id=row.event_id,
        replay_fingerprint=row.replay_fingerprint,
        correlation_id=row.correlation_id,
        job_id=row.job_id,
        endpoint=row.endpoint,
        replay_status=row.replay_status,  # type: ignore[arg-type]
        dry_run=bool(row.dry_run),
        replay_reason=row.replay_reason,
        requested_by=row.requested_by,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
    )


class IngestionJobService:
    """
    Persists ingestion lifecycle and operational controls for ingestion runbooks.
    """

    async def create_or_get_job(
        self,
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
    ) -> IngestionJobCreateResult:
        async for db in get_async_db_session():
            async with db.begin():
                if idempotency_key:
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
                        return IngestionJobCreateResult(job=_to_response(existing), created=False)

                row = DBIngestionJob(
                    job_id=job_id,
                    endpoint=endpoint,
                    entity_type=entity_type,
                    status="accepted",
                    accepted_count=accepted_count,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    request_payload=request_payload,
                )
                db.add(row)
                await db.flush()
                INGESTION_JOBS_CREATED_TOTAL.labels(
                    endpoint=endpoint, entity_type=entity_type
                ).inc()
                return IngestionJobCreateResult(job=_to_response(row), created=True)

        msg = "Unable to create ingestion job due to unavailable database session."
        raise RuntimeError(msg)

    async def mark_queued(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "queued"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = None

    async def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
        failure_phase: str = "publish",
        failed_record_keys: list[str] | None = None,
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "failed"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = failure_reason
                db.add(
                    DBIngestionJobFailure(
                        failure_id=f"fail_{uuid4().hex}",
                        job_id=job_id,
                        failure_phase=failure_phase,
                        failure_reason=failure_reason,
                        failed_record_keys=failed_record_keys or [],
                    )
                )
                INGESTION_JOBS_FAILED_TOTAL.labels(
                    endpoint=row.endpoint,
                    entity_type=row.entity_type,
                    failure_phase=failure_phase,
                ).inc()

    async def mark_retried(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.retry_count = int(row.retry_count or 0) + 1
                row.last_retried_at = datetime.now(UTC)
                INGESTION_JOBS_RETRIED_TOTAL.labels(
                    endpoint=row.endpoint, entity_type=row.entity_type, result="accepted"
                ).inc()

    async def get_job(self, job_id: str) -> IngestionJobResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            return _to_response(row) if row else None
        return None

    async def get_job_replay_context(self, job_id: str) -> IngestionJobReplayContext | None:
        async for db in get_async_db_session():
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

    async def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[IngestionJobResponse], str | None]:
        async for db in get_async_db_session():
            stmt = select(DBIngestionJob)
            if status is not None:
                stmt = stmt.where(DBIngestionJob.status == status)
            if entity_type is not None:
                stmt = stmt.where(DBIngestionJob.entity_type == entity_type)
            if submitted_from is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at >= submitted_from)
            if submitted_to is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at <= submitted_to)
            if cursor is not None:
                cursor_row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == cursor).limit(1)
                )
                if cursor_row is not None:
                    stmt = stmt.where(DBIngestionJob.id < cursor_row.id)
            stmt = stmt.order_by(desc(DBIngestionJob.id)).limit(limit + 1)
            rows = list((await db.scalars(stmt)).all())
            has_more = len(rows) > limit
            page_rows = rows[:limit]
            next_cursor = page_rows[-1].job_id if has_more and page_rows else None
            return ([_to_response(row) for row in page_rows], next_cursor)
        return ([], None)

    async def list_failures(
        self, job_id: str, limit: int = 100
    ) -> list[IngestionJobFailureResponse]:
        async for db in get_async_db_session():
            rows = (
                await db.scalars(
                    select(DBIngestionJobFailure)
                    .where(DBIngestionJobFailure.job_id == job_id)
                    .order_by(desc(DBIngestionJobFailure.failed_at))
                    .limit(limit)
                )
            ).all()
            return [_to_failure_response(row) for row in rows]
        return []

    async def get_health_summary(self) -> IngestionHealthSummaryResponse:
        async for db in get_async_db_session():
            row = (
                await db.execute(
                    select(
                        func.count(DBIngestionJob.id),
                        func.sum(
                            case((DBIngestionJob.status == "accepted", 1), else_=0)
                        ),
                        func.sum(case((DBIngestionJob.status == "queued", 1), else_=0)),
                        func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)),
                    )
                )
            ).one()
            total_jobs = int(row[0] or 0)
            accepted_jobs = int(row[1] or 0)
            queued_jobs = int(row[2] or 0)
            failed_jobs = int(row[3] or 0)
            return IngestionHealthSummaryResponse(
                total_jobs=total_jobs,
                accepted_jobs=accepted_jobs,
                queued_jobs=queued_jobs,
                failed_jobs=failed_jobs,
                backlog_jobs=accepted_jobs + queued_jobs,
            )
        return IngestionHealthSummaryResponse(
            total_jobs=0,
            accepted_jobs=0,
            queued_jobs=0,
            failed_jobs=0,
            backlog_jobs=0,
        )

    async def get_slo_status(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        queue_latency_threshold_seconds: float = 5.0,
        backlog_age_threshold_seconds: float = 300.0,
    ) -> IngestionSloStatusResponse:
        async for db in get_async_db_session():
            since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
            # Prefer DB-side aggregation (including percentile) to avoid loading all jobs in memory.
            p95_latency = 0.0
            total_jobs = 0
            failed_jobs = 0
            backlog_age_seconds = 0.0
            try:
                latency_seconds = func.extract(
                    "epoch",
                    DBIngestionJob.completed_at - DBIngestionJob.submitted_at,
                )
                row = (
                    await db.execute(
                        select(
                            func.count(DBIngestionJob.id).label("total_jobs"),
                            func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)).label(
                                "failed_jobs"
                            ),
                            func.min(
                                case(
                                    (
                                        DBIngestionJob.status.in_(["accepted", "queued"]),
                                        DBIngestionJob.submitted_at,
                                    ),
                                    else_=None,
                                )
                            ).label("oldest_backlog_submitted_at"),
                            func.percentile_cont(0.95)
                            .within_group(latency_seconds)
                            .filter(DBIngestionJob.completed_at.is_not(None))
                            .label("p95_latency"),
                        ).where(DBIngestionJob.submitted_at >= since)
                    )
                ).one()
                total_jobs = int(row[0] or 0)
                failed_jobs = int(row[1] or 0)
                oldest_backlog_submitted_at = row[2]
                p95_latency = float(row[3] or 0.0)
                if oldest_backlog_submitted_at is not None:
                    backlog_age_seconds = float(
                        (datetime.now(UTC) - oldest_backlog_submitted_at).total_seconds()
                    )
            except Exception:
                # Fallback path for dialects/environments without percentile_cont support.
                jobs = (
                    await db.scalars(
                        select(DBIngestionJob).where(DBIngestionJob.submitted_at >= since)
                    )
                ).all()
                total_jobs = len(jobs)
                failed_jobs = len([j for j in jobs if j.status == "failed"])

                latencies = [
                    (j.completed_at - j.submitted_at).total_seconds()
                    for j in jobs
                    if j.completed_at is not None
                ]
                latencies.sort()
                if latencies:
                    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
                    p95_latency = float(latencies[p95_index])

                non_terminal = [j for j in jobs if j.status in {"accepted", "queued"}]
                if non_terminal:
                    oldest = min(non_terminal, key=lambda item: item.submitted_at)
                    backlog_age_seconds = float(
                        (datetime.now(UTC) - oldest.submitted_at).total_seconds()
                    )
            INGESTION_BACKLOG_AGE_SECONDS.set(backlog_age_seconds)

            failure_rate = (
                Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
            )
            return IngestionSloStatusResponse(
                lookback_minutes=lookback_minutes,
                total_jobs=total_jobs,
                failed_jobs=failed_jobs,
                failure_rate=failure_rate,
                p95_queue_latency_seconds=p95_latency,
                backlog_age_seconds=backlog_age_seconds,
                breach_failure_rate=failure_rate > failure_rate_threshold,
                breach_queue_latency=p95_latency > queue_latency_threshold_seconds,
                breach_backlog_age=backlog_age_seconds > backlog_age_threshold_seconds,
            )
        return IngestionSloStatusResponse(
            lookback_minutes=lookback_minutes,
            total_jobs=0,
            failed_jobs=0,
            failure_rate=Decimal("0"),
            p95_queue_latency_seconds=0.0,
            backlog_age_seconds=0.0,
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
        )

    async def get_backlog_breakdown(
        self,
        *,
        lookback_minutes: int = 1440,
        limit: int = 200,
    ) -> IngestionBacklogBreakdownResponse:
        async for db in get_async_db_session():
            since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
            now_utc = datetime.now(UTC)
            rows = await db.execute(
                select(
                    DBIngestionJob.endpoint,
                    DBIngestionJob.entity_type,
                    func.count(DBIngestionJob.id).label("total_jobs"),
                    func.sum(case((DBIngestionJob.status == "accepted", 1), else_=0)).label(
                        "accepted_jobs"
                    ),
                    func.sum(case((DBIngestionJob.status == "queued", 1), else_=0)).label(
                        "queued_jobs"
                    ),
                    func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)).label(
                        "failed_jobs"
                    ),
                    func.min(
                        case(
                            (
                                DBIngestionJob.status.in_(["accepted", "queued"]),
                                DBIngestionJob.submitted_at,
                            ),
                            else_=None,
                        )
                    ).label("oldest_backlog_submitted_at"),
                )
                .where(DBIngestionJob.submitted_at >= since)
                .group_by(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
            )

            rows: list[IngestionBacklogBreakdownItemResponse] = []
            for (
                endpoint,
                entity_type,
                total_jobs_raw,
                accepted_jobs_raw,
                queued_jobs_raw,
                failed_jobs_raw,
                oldest_backlog_submitted_at,
            ) in rows:
                accepted_jobs = int(accepted_jobs_raw or 0)
                queued_jobs = int(queued_jobs_raw or 0)
                failed_jobs = int(failed_jobs_raw or 0)
                backlog_jobs = int(accepted_jobs + queued_jobs)
                oldest_backlog_age_seconds = (
                    float((now_utc - oldest_backlog_submitted_at).total_seconds())
                    if oldest_backlog_submitted_at is not None
                    else 0.0
                )
                total_jobs = int(total_jobs_raw or 0)
                failure_rate = (
                    Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
                )
                rows.append(
                    IngestionBacklogBreakdownItemResponse(
                        endpoint=endpoint,
                        entity_type=entity_type,
                        total_jobs=total_jobs,
                        accepted_jobs=accepted_jobs,
                        queued_jobs=queued_jobs,
                        failed_jobs=failed_jobs,
                        backlog_jobs=backlog_jobs,
                        oldest_backlog_submitted_at=oldest_backlog_submitted_at,
                        oldest_backlog_age_seconds=oldest_backlog_age_seconds,
                        failure_rate=failure_rate,
                    )
                )

            rows = sorted(
                rows,
                key=lambda item: (item.backlog_jobs, item.oldest_backlog_age_seconds),
                reverse=True,
            )[:limit]

            return IngestionBacklogBreakdownResponse(
                lookback_minutes=lookback_minutes,
                total_backlog_jobs=sum(item.backlog_jobs for item in rows),
                groups=rows,
            )

        return IngestionBacklogBreakdownResponse(
            lookback_minutes=lookback_minutes,
            total_backlog_jobs=0,
            groups=[],
        )

    async def list_stalled_jobs(
        self,
        *,
        threshold_seconds: int = 300,
        limit: int = 100,
    ) -> IngestionStalledJobListResponse:
        async for db in get_async_db_session():
            cutoff = datetime.now(UTC) - timedelta(seconds=threshold_seconds)
            rows = (
                await db.scalars(
                    select(DBIngestionJob)
                    .where(
                        and_(
                            DBIngestionJob.status.in_(["accepted", "queued"]),
                            DBIngestionJob.submitted_at <= cutoff,
                        )
                    )
                    .order_by(DBIngestionJob.submitted_at.asc())
                    .limit(limit)
                )
            ).all()
            now_utc = datetime.now(UTC)
            jobs: list[IngestionStalledJobResponse] = []
            for row in rows:
                queue_age_seconds = float((now_utc - row.submitted_at).total_seconds())
                suggested_action = (
                    "Investigate consumer lag and retry this job once root cause is resolved."
                    if row.status == "accepted"
                    else "Inspect downstream processing bottlenecks and verify queued job drain progress."
                )
                jobs.append(
                    IngestionStalledJobResponse(
                        job_id=row.job_id,
                        endpoint=row.endpoint,
                        entity_type=row.entity_type,
                        status=row.status,  # type: ignore[arg-type]
                        submitted_at=row.submitted_at,
                        queue_age_seconds=queue_age_seconds,
                        retry_count=row.retry_count,
                        suggested_action=suggested_action,
                    )
                )
            return IngestionStalledJobListResponse(
                threshold_seconds=threshold_seconds,
                total=len(jobs),
                jobs=jobs,
            )

        return IngestionStalledJobListResponse(
            threshold_seconds=threshold_seconds,
            total=0,
            jobs=[],
        )

    async def list_consumer_dlq_events(
        self,
        *,
        limit: int = 100,
        original_topic: str | None = None,
        consumer_group: str | None = None,
    ) -> list[ConsumerDlqEventResponse]:
        async for db in get_async_db_session():
            stmt = select(DBConsumerDlqEvent)
            if original_topic:
                stmt = stmt.where(DBConsumerDlqEvent.original_topic == original_topic)
            if consumer_group:
                stmt = stmt.where(DBConsumerDlqEvent.consumer_group == consumer_group)
            rows = (
                await db.scalars(stmt.order_by(desc(DBConsumerDlqEvent.observed_at)).limit(limit))
            ).all()
            return [_to_dlq_event_response(row) for row in rows]
        return []

    async def get_consumer_dlq_event(self, event_id: str) -> ConsumerDlqEventResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBConsumerDlqEvent).where(DBConsumerDlqEvent.event_id == event_id).limit(1)
            )
            return _to_dlq_event_response(row) if row else None
        return None

    async def find_successful_replay_audit_by_fingerprint(
        self,
        replay_fingerprint: str,
        recovery_path: str | None = None,
    ) -> dict[str, str] | None:
        async for db in get_async_db_session():
            stmt = select(DBConsumerDlqReplayAudit).where(
                and_(
                    DBConsumerDlqReplayAudit.replay_fingerprint == replay_fingerprint,
                    DBConsumerDlqReplayAudit.replay_status == "replayed",
                )
            )
            if recovery_path is not None:
                stmt = stmt.where(DBConsumerDlqReplayAudit.recovery_path == recovery_path)
            row = await db.scalar(
                stmt.order_by(desc(DBConsumerDlqReplayAudit.requested_at)).limit(1)
            )
            if row is None:
                return None
            return {"replay_id": row.replay_id, "replay_status": row.replay_status}
        return None

    async def record_consumer_dlq_replay_audit(
        self,
        *,
        recovery_path: str,
        event_id: str,
        replay_fingerprint: str,
        correlation_id: str | None,
        job_id: str | None,
        endpoint: str | None,
        replay_status: str,
        dry_run: bool,
        replay_reason: str,
        requested_by: str | None,
    ) -> str:
        replay_id = f"replay_{uuid4().hex}"
        async for db in get_async_db_session():
            async with db.begin():
                db.add(
                    DBConsumerDlqReplayAudit(
                        replay_id=replay_id,
                        recovery_path=recovery_path,
                        event_id=event_id,
                        replay_fingerprint=replay_fingerprint,
                        correlation_id=correlation_id,
                        job_id=job_id,
                        endpoint=endpoint,
                        replay_status=replay_status,
                        dry_run=dry_run,
                        replay_reason=replay_reason,
                        requested_by=requested_by,
                        completed_at=datetime.now(UTC),
                    )
                )
            INGESTION_REPLAY_AUDIT_TOTAL.labels(
                recovery_path=recovery_path, replay_status=replay_status
            ).inc()
            if replay_status == "duplicate_blocked":
                INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL.labels(recovery_path=recovery_path).inc()
            if replay_status in {"not_replayable", "failed"}:
                INGESTION_REPLAY_FAILURE_TOTAL.labels(
                    recovery_path=recovery_path, replay_status=replay_status
                ).inc()
            return replay_id
        raise RuntimeError("Unable to record consumer DLQ replay audit.")

    async def get_replay_audit(self, replay_id: str) -> IngestionReplayAuditResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBConsumerDlqReplayAudit)
                .where(DBConsumerDlqReplayAudit.replay_id == replay_id)
                .limit(1)
            )
            return _to_replay_audit_response(row) if row else None
        return None

    async def list_replay_audits(
        self,
        *,
        limit: int = 100,
        recovery_path: str | None = None,
        replay_status: str | None = None,
        replay_fingerprint: str | None = None,
        job_id: str | None = None,
    ) -> list[IngestionReplayAuditResponse]:
        async for db in get_async_db_session():
            stmt = select(DBConsumerDlqReplayAudit)
            if recovery_path:
                stmt = stmt.where(DBConsumerDlqReplayAudit.recovery_path == recovery_path)
            if replay_status:
                stmt = stmt.where(DBConsumerDlqReplayAudit.replay_status == replay_status)
            if replay_fingerprint:
                stmt = stmt.where(DBConsumerDlqReplayAudit.replay_fingerprint == replay_fingerprint)
            if job_id:
                stmt = stmt.where(DBConsumerDlqReplayAudit.job_id == job_id)
            rows = (
                await db.scalars(
                    stmt.order_by(desc(DBConsumerDlqReplayAudit.requested_at)).limit(limit)
                )
            ).all()
            return [_to_replay_audit_response(row) for row in rows]
        return []

    async def get_consumer_lag(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 100,
    ) -> IngestionConsumerLagResponse:
        async for db in get_async_db_session():
            since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
            groups: list[IngestionConsumerLagGroupResponse] = []
            rows = await db.execute(
                select(
                    DBConsumerDlqEvent.consumer_group,
                    DBConsumerDlqEvent.original_topic,
                    func.count(DBConsumerDlqEvent.id).label("dlq_events"),
                    func.max(DBConsumerDlqEvent.observed_at).label("last_observed_at"),
                )
                .where(DBConsumerDlqEvent.observed_at >= since)
                .group_by(DBConsumerDlqEvent.consumer_group, DBConsumerDlqEvent.original_topic)
                .order_by(desc("dlq_events"), desc("last_observed_at"))
                .limit(limit)
            )
            for consumer_group, original_topic, dlq_events_raw, last_observed_at in rows:
                dlq_events = int(dlq_events_raw or 0)
                if dlq_events >= 20:
                    severity = "high"
                elif dlq_events >= 5:
                    severity = "medium"
                else:
                    severity = "low"
                groups.append(
                    IngestionConsumerLagGroupResponse(
                        consumer_group=consumer_group,
                        original_topic=original_topic,
                        dlq_events=dlq_events,
                        last_observed_at=last_observed_at,
                        lag_severity=severity,  # type: ignore[arg-type]
                    )
                )
            backlog = await self.get_health_summary()
            return IngestionConsumerLagResponse(
                lookback_minutes=lookback_minutes,
                backlog_jobs=backlog.backlog_jobs,
                total_groups=len(groups),
                groups=groups,
            )

        return IngestionConsumerLagResponse(
            lookback_minutes=lookback_minutes,
            backlog_jobs=0,
            total_groups=0,
            groups=[],
        )

    async def get_job_record_status(self, job_id: str) -> IngestionJobRecordStatusResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            if row is None:
                return None
            failures = (
                await db.scalars(
                    select(DBIngestionJobFailure)
                    .where(DBIngestionJobFailure.job_id == job_id)
                    .order_by(desc(DBIngestionJobFailure.failed_at))
                )
            ).all()

            failed_keys: set[str] = set()
            for failure in failures:
                for item in list(failure.failed_record_keys or []):
                    if isinstance(item, str):
                        failed_keys.add(item)

            payload = row.request_payload if isinstance(row.request_payload, dict) else {}
            replayable_keys: list[str] = []
            if row.endpoint == "/ingest/transactions":
                replayable_keys = [
                    str(item.get("transaction_id"))
                    for item in payload.get("transactions", [])
                    if item.get("transaction_id")
                ]
            elif row.endpoint == "/ingest/portfolios":
                replayable_keys = [
                    str(item.get("portfolio_id"))
                    for item in payload.get("portfolios", [])
                    if item.get("portfolio_id")
                ]
            elif row.endpoint == "/ingest/instruments":
                replayable_keys = [
                    str(item.get("security_id"))
                    for item in payload.get("instruments", [])
                    if item.get("security_id")
                ]
            elif row.endpoint == "/ingest/business-dates":
                replayable_keys = [
                    str(item.get("business_date"))
                    for item in payload.get("business_dates", [])
                    if item.get("business_date")
                ]

            return IngestionJobRecordStatusResponse(
                job_id=row.job_id,
                entity_type=row.entity_type,
                accepted_count=row.accepted_count,
                failed_record_keys=sorted(failed_keys),
                replayable_record_keys=replayable_keys,
            )
        return None

    async def get_idempotency_diagnostics(
        self,
        *,
        lookback_minutes: int = 1440,
        limit: int = 200,
    ) -> IngestionIdempotencyDiagnosticsResponse:
        async for db in get_async_db_session():
            since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
            items: list[IngestionIdempotencyDiagnosticItemResponse] = []
            rows = await db.execute(
                select(
                    DBIngestionJob.idempotency_key,
                    func.count(DBIngestionJob.id).label("usage_count"),
                    func.count(func.distinct(DBIngestionJob.endpoint)).label("endpoint_count"),
                    func.array_agg(func.distinct(DBIngestionJob.endpoint)).label("endpoints"),
                    func.min(DBIngestionJob.submitted_at).label("first_seen_at"),
                    func.max(DBIngestionJob.submitted_at).label("last_seen_at"),
                )
                .where(
                    and_(
                        DBIngestionJob.submitted_at >= since,
                        DBIngestionJob.idempotency_key.is_not(None),
                    )
                )
                .group_by(DBIngestionJob.idempotency_key)
                .order_by(desc("usage_count"))
                .limit(limit)
            )
            collisions = 0
            for (
                key,
                usage_count_raw,
                endpoint_count_raw,
                endpoints_raw,
                first_seen_at,
                last_seen_at,
            ) in rows:
                usage_count = int(usage_count_raw or 0)
                endpoint_count = int(endpoint_count_raw or 0)
                endpoints = sorted(list(endpoints_raw or []))
                collision_detected = endpoint_count > 1
                if collision_detected:
                    collisions += 1
                items.append(
                    IngestionIdempotencyDiagnosticItemResponse(
                        idempotency_key=key,
                        usage_count=usage_count,
                        endpoint_count=endpoint_count,
                        endpoints=endpoints,
                        first_seen_at=first_seen_at,
                        last_seen_at=last_seen_at,
                        collision_detected=collision_detected,
                    )
                )

            return IngestionIdempotencyDiagnosticsResponse(
                lookback_minutes=lookback_minutes,
                total_keys=len(items),
                collisions=collisions,
                keys=items,
            )
        return IngestionIdempotencyDiagnosticsResponse(
            lookback_minutes=lookback_minutes,
            total_keys=0,
            collisions=0,
            keys=[],
        )

    async def get_error_budget_status(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        backlog_growth_threshold: int = 5,
    ) -> IngestionErrorBudgetStatusResponse:
        async for db in get_async_db_session():
            now_utc = datetime.now(UTC)
            current_since = now_utc - timedelta(minutes=lookback_minutes)
            previous_since = now_utc - timedelta(minutes=lookback_minutes * 2)
            current_row = (
                await db.execute(
                    select(
                        func.count(DBIngestionJob.id).label("total_jobs"),
                        func.sum(case((DBIngestionJob.status == "failed", 1), else_=0)).label(
                            "failed_jobs"
                        ),
                        func.sum(
                            case(
                                (DBIngestionJob.status.in_(["accepted", "queued"]), 1),
                                else_=0,
                            )
                        ).label("backlog_jobs"),
                    ).where(DBIngestionJob.submitted_at >= current_since)
                )
            ).one()
            previous_row = (
                await db.execute(
                    select(
                        func.sum(
                            case(
                                (DBIngestionJob.status.in_(["accepted", "queued"]), 1),
                                else_=0,
                            )
                        ).label("previous_backlog_jobs"),
                    ).where(
                        and_(
                            DBIngestionJob.submitted_at >= previous_since,
                            DBIngestionJob.submitted_at < current_since,
                        )
                    )
                )
            ).one()

            total_jobs = int(current_row[0] or 0)
            failed_jobs = int(current_row[1] or 0)
            failure_rate = (
                Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
            )
            remaining_budget = max(Decimal("0"), failure_rate_threshold - failure_rate)
            backlog_jobs = int(current_row[2] or 0)
            previous_backlog_jobs = int(previous_row[0] or 0)
            backlog_growth = backlog_jobs - previous_backlog_jobs

            return IngestionErrorBudgetStatusResponse(
                lookback_minutes=lookback_minutes,
                previous_lookback_minutes=lookback_minutes,
                total_jobs=total_jobs,
                failed_jobs=failed_jobs,
                failure_rate=failure_rate,
                remaining_error_budget=remaining_budget,
                backlog_jobs=backlog_jobs,
                previous_backlog_jobs=previous_backlog_jobs,
                backlog_growth=backlog_growth,
                breach_failure_rate=failure_rate > failure_rate_threshold,
                breach_backlog_growth=backlog_growth > backlog_growth_threshold,
            )
        return IngestionErrorBudgetStatusResponse(
            lookback_minutes=lookback_minutes,
            previous_lookback_minutes=lookback_minutes,
            total_jobs=0,
            failed_jobs=0,
            failure_rate=Decimal("0"),
            remaining_error_budget=failure_rate_threshold,
            backlog_jobs=0,
            previous_backlog_jobs=0,
            backlog_growth=0,
            breach_failure_rate=False,
            breach_backlog_growth=False,
        )

    async def get_ops_mode(self) -> IngestionOpsModeResponse:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
            )
            if row is None:
                row = DBIngestionOpsControl(
                    id=1,
                    mode="normal",
                    replay_window_start=None,
                    replay_window_end=None,
                    updated_by="system_bootstrap",
                )
                async with db.begin():
                    db.add(row)
                    await db.flush()
            return IngestionOpsModeResponse(
                mode=row.mode,  # type: ignore[arg-type]
                replay_window_start=row.replay_window_start,
                replay_window_end=row.replay_window_end,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )
        raise RuntimeError("Unable to read ingestion ops mode.")

    async def update_ops_mode(
        self,
        *,
        mode: str,
        replay_window_start: datetime | None,
        replay_window_end: datetime | None,
        updated_by: str | None,
    ) -> IngestionOpsModeResponse:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
                )
                if row is None:
                    row = DBIngestionOpsControl(id=1, mode="normal")
                    db.add(row)
                    await db.flush()
                row.mode = mode
                row.replay_window_start = replay_window_start
                row.replay_window_end = replay_window_end
                row.updated_by = updated_by
                row.updated_at = datetime.now(UTC)
            return IngestionOpsModeResponse(
                mode=row.mode,  # type: ignore[arg-type]
                replay_window_start=row.replay_window_start,
                replay_window_end=row.replay_window_end,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )
        raise RuntimeError("Unable to update ingestion ops mode.")

    async def assert_ingestion_writable(self) -> None:
        mode = await self.get_ops_mode()
        INGESTION_MODE_STATE.set({"normal": 0, "paused": 1, "drain": 2}[mode.mode])
        if mode.mode in {"paused", "drain"}:
            raise PermissionError(
                f"Ingestion is currently in '{mode.mode}' mode and not accepting new requests."
            )

    async def assert_retry_allowed(self, submitted_at: datetime) -> None:
        await self.assert_retry_allowed_for_records(submitted_at=submitted_at, replay_record_count=1)

    async def _count_backlog_jobs(self) -> int:
        async for db in get_async_db_session():
            backlog = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status.in_(("accepted", "queued"))
                        )
                    )
                )
                or 0
            )
            return backlog
        return 0

    async def assert_retry_allowed_for_records(
        self,
        *,
        submitted_at: datetime,
        replay_record_count: int,
    ) -> None:
        mode = await self.get_ops_mode()
        if mode.mode == "paused":
            raise PermissionError("Retries are blocked while ingestion is paused.")
        now = datetime.now(UTC)
        if mode.replay_window_start and now < mode.replay_window_start:
            raise PermissionError("Current time is before configured replay window.")
        if mode.replay_window_end and now > mode.replay_window_end:
            raise PermissionError("Current time is after configured replay window.")
        if now < submitted_at:
            raise PermissionError("Retry blocked: job submission timestamp is in the future.")
        if replay_record_count > REPLAY_MAX_RECORDS_PER_REQUEST:
            raise PermissionError(
                "Retry blocked: requested replay record count exceeds configured limit. "
                f"requested_records={replay_record_count}, "
                f"max_records={REPLAY_MAX_RECORDS_PER_REQUEST}."
            )
        backlog_jobs = await self._count_backlog_jobs()
        if backlog_jobs >= REPLAY_MAX_BACKLOG_JOBS:
            raise PermissionError(
                "Retry blocked: ingestion backlog exceeds configured replay safety threshold. "
                f"backlog_jobs={backlog_jobs}, max_backlog_jobs={REPLAY_MAX_BACKLOG_JOBS}."
            )

    async def assert_reprocessing_publish_allowed(self, record_count: int) -> None:
        now = datetime.now(UTC)
        await self.assert_retry_allowed_for_records(
            submitted_at=now,
            replay_record_count=max(1, int(record_count)),
        )


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
