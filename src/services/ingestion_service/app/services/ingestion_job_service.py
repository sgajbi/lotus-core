from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from portfolio_common.database_models import ConsumerDlqEvent as DBConsumerDlqEvent
from portfolio_common.database_models import ConsumerDlqReplayAudit as DBConsumerDlqReplayAudit
from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from portfolio_common.database_models import IngestionOpsControl as DBIngestionOpsControl
from portfolio_common.database_models import ReprocessingJob as DBReprocessingJob
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
from sqlalchemy import and_, case, desc, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from ..DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionBacklogBreakdownItemResponse,
    IngestionBacklogBreakdownResponse,
    IngestionCapacityGroupResponse,
    IngestionCapacityStatusResponse,
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
    IngestionOperatingBandResponse,
    IngestionOpsModeResponse,
    IngestionOpsPolicyResponse,
    IngestionReplayAuditResponse,
    IngestionReprocessingQueueHealthResponse,
    IngestionReprocessingQueueItemResponse,
    IngestionSloStatusResponse,
    IngestionStalledJobListResponse,
    IngestionStalledJobResponse,
)
from ..settings import get_ingestion_service_settings

_SETTINGS = get_ingestion_service_settings()
_RUNTIME_POLICY = _SETTINGS.runtime_policy

REPLAY_MAX_RECORDS_PER_REQUEST = _RUNTIME_POLICY.replay_max_records_per_request
REPLAY_MAX_BACKLOG_JOBS = _RUNTIME_POLICY.replay_max_backlog_jobs
DLQ_BUDGET_EVENTS_PER_WINDOW = _RUNTIME_POLICY.dlq_budget_events_per_window
DEFAULT_LOOKBACK_MINUTES = _RUNTIME_POLICY.default_lookback_minutes
DEFAULT_FAILURE_RATE_THRESHOLD = _RUNTIME_POLICY.default_failure_rate_threshold
DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS = _RUNTIME_POLICY.default_queue_latency_threshold_seconds
DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS = _RUNTIME_POLICY.default_backlog_age_threshold_seconds
REPROCESSING_WORKER_POLL_INTERVAL_SECONDS = (
    _RUNTIME_POLICY.reprocessing_worker_poll_interval_seconds
)
REPROCESSING_WORKER_BATCH_SIZE = _RUNTIME_POLICY.reprocessing_worker_batch_size
VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS = (
    _RUNTIME_POLICY.valuation_scheduler_poll_interval_seconds
)
VALUATION_SCHEDULER_BATCH_SIZE = _RUNTIME_POLICY.valuation_scheduler_batch_size
VALUATION_SCHEDULER_DISPATCH_ROUNDS = _RUNTIME_POLICY.valuation_scheduler_dispatch_rounds
CAPACITY_ASSUMED_REPLICAS = _RUNTIME_POLICY.capacity_assumed_replicas
REPLAY_ISOLATION_MODE = _RUNTIME_POLICY.replay_isolation_mode
PARTITION_GROWTH_STRATEGY = _RUNTIME_POLICY.partition_growth_strategy
CALCULATOR_PEAK_LAG_AGE_SECONDS = dict(_RUNTIME_POLICY.calculator_peak_lag_age_seconds)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OperatingBandPolicy:
    yellow_backlog_age_seconds: float
    orange_backlog_age_seconds: float
    red_backlog_age_seconds: float
    yellow_dlq_pressure_ratio: Decimal
    orange_dlq_pressure_ratio: Decimal
    red_dlq_pressure_ratio: Decimal


@dataclass(frozen=True, slots=True)
class OperatingBandSignals:
    backlog_age_seconds: float
    dlq_pressure_ratio: Decimal
    breach_failure_rate: bool
    breach_queue_latency: bool
    breach_backlog_age: bool
    failure_rate: Decimal


@dataclass(frozen=True, slots=True)
class OperatingBandDecision:
    operating_band: Literal["green", "yellow", "orange", "red"]
    recommended_action: str
    triggered_signals: list[str]


OPERATING_BAND_POLICY = OperatingBandPolicy(
    yellow_backlog_age_seconds=_RUNTIME_POLICY.operating_band.yellow_backlog_age_seconds,
    orange_backlog_age_seconds=_RUNTIME_POLICY.operating_band.orange_backlog_age_seconds,
    red_backlog_age_seconds=_RUNTIME_POLICY.operating_band.red_backlog_age_seconds,
    yellow_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.yellow_dlq_pressure_ratio,
    orange_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.orange_dlq_pressure_ratio,
    red_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.red_dlq_pressure_ratio,
)


def classify_operating_band(
    *,
    signals: OperatingBandSignals,
    policy: OperatingBandPolicy = OPERATING_BAND_POLICY,
) -> OperatingBandDecision:
    triggered_signals: list[str] = []
    if (
        signals.backlog_age_seconds >= policy.red_backlog_age_seconds
        or signals.dlq_pressure_ratio >= policy.red_dlq_pressure_ratio
    ):
        if signals.backlog_age_seconds >= policy.red_backlog_age_seconds:
            triggered_signals.append(f"backlog_age_seconds>={int(policy.red_backlog_age_seconds)}")
        if signals.dlq_pressure_ratio >= policy.red_dlq_pressure_ratio:
            triggered_signals.append(
                f"dlq_pressure_ratio>={policy.red_dlq_pressure_ratio.normalize()}"
            )
        return OperatingBandDecision(
            operating_band="red",
            recommended_action=(
                "Enter incident mode and block non-emergency replay until lag pressure stabilizes."
            ),
            triggered_signals=triggered_signals,
        )

    if (
        signals.backlog_age_seconds >= policy.orange_backlog_age_seconds
        or signals.dlq_pressure_ratio >= policy.orange_dlq_pressure_ratio
        or signals.breach_failure_rate
        or signals.breach_queue_latency
        or signals.breach_backlog_age
    ):
        if signals.backlog_age_seconds >= policy.orange_backlog_age_seconds:
            triggered_signals.append(
                f"backlog_age_seconds>={int(policy.orange_backlog_age_seconds)}"
            )
        if signals.dlq_pressure_ratio >= policy.orange_dlq_pressure_ratio:
            triggered_signals.append(
                f"dlq_pressure_ratio>={policy.orange_dlq_pressure_ratio.normalize()}"
            )
        if signals.breach_failure_rate:
            triggered_signals.append("breach_failure_rate")
        if signals.breach_queue_latency:
            triggered_signals.append("breach_queue_latency")
        if signals.breach_backlog_age:
            triggered_signals.append("breach_backlog_age")
        return OperatingBandDecision(
            operating_band="orange",
            recommended_action=(
                "Aggressively scale calculators and pause non-critical replay operations."
            ),
            triggered_signals=triggered_signals,
        )

    if (
        signals.backlog_age_seconds >= policy.yellow_backlog_age_seconds
        or signals.dlq_pressure_ratio >= policy.yellow_dlq_pressure_ratio
    ):
        if signals.backlog_age_seconds >= policy.yellow_backlog_age_seconds:
            triggered_signals.append(
                f"backlog_age_seconds>={int(policy.yellow_backlog_age_seconds)}"
            )
        if signals.dlq_pressure_ratio >= policy.yellow_dlq_pressure_ratio:
            triggered_signals.append(
                f"dlq_pressure_ratio>={policy.yellow_dlq_pressure_ratio.normalize()}"
            )
        return OperatingBandDecision(
            operating_band="yellow",
            recommended_action="Scale up one band and monitor DLQ pressure.",
            triggered_signals=triggered_signals,
        )

    return OperatingBandDecision(
        operating_band="green",
        recommended_action="Hold baseline replicas.",
        triggered_signals=["stable_signals"],
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


_SUCCESSFUL_REPLAY_AUDIT_STATUSES = {"replayed", "replayed_bookkeeping_failed"}
_FAILED_REPLAY_AUDIT_STATUSES = {"not_replayable", "failed", "replayed_bookkeeping_failed"}


def _derive_capacity_group(
    *,
    endpoint: str,
    entity_type: str,
    total_records: int,
    processed_records: int,
    backlog_records: int,
    backlog_jobs: int,
    lookback_seconds: Decimal,
    assumed_replicas: int,
) -> IngestionCapacityGroupResponse:
    safe_lookback_seconds = max(lookback_seconds, Decimal("1"))
    safe_replicas = max(assumed_replicas, 1)
    decimal_total_records = Decimal(total_records)
    decimal_processed_records = Decimal(processed_records)
    decimal_backlog_records = Decimal(backlog_records)

    lambda_in = decimal_total_records / safe_lookback_seconds
    mu_msg_per_replica = decimal_processed_records / safe_lookback_seconds
    effective_capacity = mu_msg_per_replica * Decimal(safe_replicas)

    if effective_capacity > Decimal("0"):
        utilization_ratio = lambda_in / effective_capacity
    else:
        utilization_ratio = Decimal("0")
    headroom_ratio = Decimal("1") - utilization_ratio

    drain_denominator = effective_capacity - lambda_in
    if decimal_backlog_records > Decimal("0") and drain_denominator > Decimal("0"):
        estimated_drain_seconds = float(decimal_backlog_records / drain_denominator)
    else:
        estimated_drain_seconds = None

    if utilization_ratio >= Decimal("1"):
        saturation_state: Literal["stable", "near_capacity", "over_capacity"] = "over_capacity"
    elif utilization_ratio >= Decimal("0.8"):
        saturation_state = "near_capacity"
    else:
        saturation_state = "stable"

    return IngestionCapacityGroupResponse(
        endpoint=endpoint,
        entity_type=entity_type,
        total_records=total_records,
        processed_records=processed_records,
        backlog_records=backlog_records,
        backlog_jobs=backlog_jobs,
        lambda_in_events_per_second=lambda_in,
        mu_msg_per_replica_events_per_second=mu_msg_per_replica,
        assumed_replicas=safe_replicas,
        effective_capacity_events_per_second=effective_capacity,
        utilization_ratio=utilization_ratio,
        headroom_ratio=headroom_ratio,
        estimated_drain_seconds=estimated_drain_seconds,
        saturation_state=saturation_state,
    )


class IngestionJobService:
    """
    Persists ingestion lifecycle and operational controls for ingestion runbooks.
    """

    @staticmethod
    def _default_slo_status(
        *,
        lookback_minutes: int,
    ) -> IngestionSloStatusResponse:
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

    @staticmethod
    def _default_error_budget_status(
        *,
        lookback_minutes: int,
        failure_rate_threshold: Decimal,
    ) -> IngestionErrorBudgetStatusResponse:
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
            replay_backlog_pressure_ratio=Decimal("0"),
            dlq_events_in_window=0,
            dlq_budget_events_per_window=max(1, DLQ_BUDGET_EVENTS_PER_WINDOW),
            dlq_pressure_ratio=Decimal("0"),
            breach_failure_rate=False,
            breach_backlog_growth=False,
        )

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
                await db.execute(
                    update(DBIngestionJob)
                    .where(DBIngestionJob.job_id == job_id)
                    .values(
                        status="queued",
                        completed_at=datetime.now(UTC),
                        failure_reason=None,
                    )
                )

    async def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
        failure_phase: str = "publish",
        failed_record_keys: list[str] | None = None,
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                updated = await db.execute(
                    update(DBIngestionJob)
                    .where(DBIngestionJob.job_id == job_id)
                    .values(
                        status="failed",
                        completed_at=datetime.now(UTC),
                        failure_reason=failure_reason,
                    )
                    .returning(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
                )
                row = updated.first()
                if row is None:
                    return
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
                updated = await db.execute(
                    update(DBIngestionJob)
                    .where(DBIngestionJob.job_id == job_id)
                    .values(
                        retry_count=func.coalesce(DBIngestionJob.retry_count, 0) + 1,
                        last_retried_at=datetime.now(UTC),
                    )
                    .returning(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
                )
                row = updated.first()
                if row is None:
                    return
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
                        func.sum(case((DBIngestionJob.status == "accepted", 1), else_=0)),
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
                latency_seconds = case(
                    (
                        DBIngestionJob.completed_at.is_not(None),
                        func.extract(
                            "epoch",
                            DBIngestionJob.completed_at - DBIngestionJob.submitted_at,
                        ),
                    ),
                    else_=None,
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
            except SQLAlchemyError:
                # Fallback path for dialects/environments without percentile_cont support.
                try:
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
                        p95_index = max(
                            0,
                            min(len(latencies) - 1, int(len(latencies) * 0.95) - 1),
                        )
                        p95_latency = float(latencies[p95_index])

                    non_terminal = [j for j in jobs if j.status in {"accepted", "queued"}]
                    if non_terminal:
                        oldest = min(non_terminal, key=lambda item: item.submitted_at)
                        backlog_age_seconds = float(
                            (datetime.now(UTC) - oldest.submitted_at).total_seconds()
                        )
                except SQLAlchemyError as exc:
                    logger.warning(
                        "ingestion_slo_status_fallback_unavailable",
                        extra={"lookback_minutes": lookback_minutes},
                        exc_info=exc,
                    )
                    return self._default_slo_status(lookback_minutes=lookback_minutes)
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
        return self._default_slo_status(lookback_minutes=lookback_minutes)

    async def get_operating_band(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        queue_latency_threshold_seconds: float = 5.0,
        backlog_age_threshold_seconds: float = 300.0,
    ) -> IngestionOperatingBandResponse:
        slo_status = await self.get_slo_status(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            queue_latency_threshold_seconds=queue_latency_threshold_seconds,
            backlog_age_threshold_seconds=backlog_age_threshold_seconds,
        )
        error_budget = await self.get_error_budget_status(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
        )
        backlog_age_seconds = float(slo_status.backlog_age_seconds)
        dlq_pressure_ratio = Decimal(error_budget.dlq_pressure_ratio)
        failure_rate = Decimal(slo_status.failure_rate)
        decision = classify_operating_band(
            signals=OperatingBandSignals(
                backlog_age_seconds=backlog_age_seconds,
                dlq_pressure_ratio=dlq_pressure_ratio,
                breach_failure_rate=bool(slo_status.breach_failure_rate),
                breach_queue_latency=bool(slo_status.breach_queue_latency),
                breach_backlog_age=bool(slo_status.breach_backlog_age),
                failure_rate=failure_rate,
            )
        )

        return IngestionOperatingBandResponse(
            lookback_minutes=lookback_minutes,
            operating_band=decision.operating_band,
            recommended_action=decision.recommended_action,
            backlog_age_seconds=backlog_age_seconds,
            dlq_pressure_ratio=dlq_pressure_ratio,
            failure_rate=failure_rate,
            triggered_signals=decision.triggered_signals,
        )

    async def get_operating_policy(self) -> IngestionOpsPolicyResponse:
        replay_isolation_mode = (
            REPLAY_ISOLATION_MODE
            if REPLAY_ISOLATION_MODE in {"shared_workers", "dedicated_workers"}
            else "shared_workers"
        )
        partition_growth_strategy = (
            PARTITION_GROWTH_STRATEGY
            if PARTITION_GROWTH_STRATEGY in {"scale_out_only", "pre_shard_large_portfolios"}
            else "scale_out_only"
        )
        calculator_peak_lag_age_seconds = {
            key: max(1, int(value)) for key, value in CALCULATOR_PEAK_LAG_AGE_SECONDS.items()
        }
        values = {
            "lookback_minutes_default": DEFAULT_LOOKBACK_MINUTES,
            "failure_rate_threshold_default": str(DEFAULT_FAILURE_RATE_THRESHOLD),
            "queue_latency_threshold_seconds_default": DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS,
            "backlog_age_threshold_seconds_default": DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS,
            "replay_max_records_per_request": max(1, REPLAY_MAX_RECORDS_PER_REQUEST),
            "replay_max_backlog_jobs": max(1, REPLAY_MAX_BACKLOG_JOBS),
            "reprocessing_worker_poll_interval_seconds": max(
                1, REPROCESSING_WORKER_POLL_INTERVAL_SECONDS
            ),
            "reprocessing_worker_batch_size": max(1, REPROCESSING_WORKER_BATCH_SIZE),
            "valuation_scheduler_poll_interval_seconds": max(
                1, VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS
            ),
            "valuation_scheduler_batch_size": max(1, VALUATION_SCHEDULER_BATCH_SIZE),
            "valuation_scheduler_dispatch_rounds": max(1, VALUATION_SCHEDULER_DISPATCH_ROUNDS),
            "dlq_budget_events_per_window": max(1, DLQ_BUDGET_EVENTS_PER_WINDOW),
            "operating_band_yellow_backlog_age_seconds": (
                OPERATING_BAND_POLICY.yellow_backlog_age_seconds
            ),
            "operating_band_orange_backlog_age_seconds": (
                OPERATING_BAND_POLICY.orange_backlog_age_seconds
            ),
            "operating_band_red_backlog_age_seconds": OPERATING_BAND_POLICY.red_backlog_age_seconds,
            "operating_band_yellow_dlq_pressure_ratio": str(
                OPERATING_BAND_POLICY.yellow_dlq_pressure_ratio
            ),
            "operating_band_orange_dlq_pressure_ratio": str(
                OPERATING_BAND_POLICY.orange_dlq_pressure_ratio
            ),
            "operating_band_red_dlq_pressure_ratio": str(
                OPERATING_BAND_POLICY.red_dlq_pressure_ratio
            ),
            "calculator_peak_lag_age_seconds": calculator_peak_lag_age_seconds,
            "replay_isolation_mode": replay_isolation_mode,
            "partition_growth_strategy": partition_growth_strategy,
            "replay_dry_run_supported": True,
        }
        serialized = json.dumps(values, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return IngestionOpsPolicyResponse(
            policy_version="v1",
            policy_fingerprint=fingerprint,
            lookback_minutes_default=DEFAULT_LOOKBACK_MINUTES,
            failure_rate_threshold_default=DEFAULT_FAILURE_RATE_THRESHOLD,
            queue_latency_threshold_seconds_default=DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS,
            backlog_age_threshold_seconds_default=DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS,
            replay_max_records_per_request=max(1, REPLAY_MAX_RECORDS_PER_REQUEST),
            replay_max_backlog_jobs=max(1, REPLAY_MAX_BACKLOG_JOBS),
            reprocessing_worker_poll_interval_seconds=max(
                1, REPROCESSING_WORKER_POLL_INTERVAL_SECONDS
            ),
            reprocessing_worker_batch_size=max(1, REPROCESSING_WORKER_BATCH_SIZE),
            valuation_scheduler_poll_interval_seconds=max(
                1, VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS
            ),
            valuation_scheduler_batch_size=max(1, VALUATION_SCHEDULER_BATCH_SIZE),
            valuation_scheduler_dispatch_rounds=max(1, VALUATION_SCHEDULER_DISPATCH_ROUNDS),
            dlq_budget_events_per_window=max(1, DLQ_BUDGET_EVENTS_PER_WINDOW),
            operating_band_yellow_backlog_age_seconds=OPERATING_BAND_POLICY.yellow_backlog_age_seconds,
            operating_band_orange_backlog_age_seconds=OPERATING_BAND_POLICY.orange_backlog_age_seconds,
            operating_band_red_backlog_age_seconds=OPERATING_BAND_POLICY.red_backlog_age_seconds,
            operating_band_yellow_dlq_pressure_ratio=OPERATING_BAND_POLICY.yellow_dlq_pressure_ratio,
            operating_band_orange_dlq_pressure_ratio=OPERATING_BAND_POLICY.orange_dlq_pressure_ratio,
            operating_band_red_dlq_pressure_ratio=OPERATING_BAND_POLICY.red_dlq_pressure_ratio,
            calculator_peak_lag_age_seconds=calculator_peak_lag_age_seconds,
            replay_isolation_mode=replay_isolation_mode,  # type: ignore[arg-type]
            partition_growth_strategy=partition_growth_strategy,  # type: ignore[arg-type]
            replay_dry_run_supported=True,
        )

    async def get_reprocessing_queue_health(self) -> IngestionReprocessingQueueHealthResponse:
        now = datetime.now(UTC)
        async for db in get_async_db_session():
            stmt = select(
                DBReprocessingJob.job_type.label("job_type"),
                func.sum(case((DBReprocessingJob.status == "PENDING", 1), else_=0)).label(
                    "pending_jobs"
                ),
                func.sum(case((DBReprocessingJob.status == "PROCESSING", 1), else_=0)).label(
                    "processing_jobs"
                ),
                func.sum(case((DBReprocessingJob.status == "FAILED", 1), else_=0)).label(
                    "failed_jobs"
                ),
                func.min(
                    case(
                        (DBReprocessingJob.status == "PENDING", DBReprocessingJob.created_at),
                        else_=None,
                    )
                ).label("oldest_pending_created_at"),
            ).group_by(DBReprocessingJob.job_type)
            result = await db.execute(stmt)
            rows = result.mappings().all()

        queue_items: list[IngestionReprocessingQueueItemResponse] = []
        total_pending = 0
        total_processing = 0
        total_failed = 0
        for row in rows:
            oldest_pending_created_at = row["oldest_pending_created_at"]
            oldest_pending_age_seconds = (
                max(0.0, (now - oldest_pending_created_at).total_seconds())
                if oldest_pending_created_at
                else 0.0
            )
            pending_jobs = int(row["pending_jobs"] or 0)
            processing_jobs = int(row["processing_jobs"] or 0)
            failed_jobs = int(row["failed_jobs"] or 0)
            queue_items.append(
                IngestionReprocessingQueueItemResponse(
                    job_type=row["job_type"],
                    pending_jobs=pending_jobs,
                    processing_jobs=processing_jobs,
                    failed_jobs=failed_jobs,
                    oldest_pending_created_at=oldest_pending_created_at,
                    oldest_pending_age_seconds=oldest_pending_age_seconds,
                )
            )
            total_pending += pending_jobs
            total_processing += processing_jobs
            total_failed += failed_jobs

        queue_items.sort(
            key=lambda item: (
                item.pending_jobs,
                item.processing_jobs,
                item.oldest_pending_age_seconds,
                item.job_type,
            ),
            reverse=True,
        )
        return IngestionReprocessingQueueHealthResponse(
            as_of=now,
            total_pending_jobs=total_pending,
            total_processing_jobs=total_processing,
            total_failed_jobs=total_failed,
            queues=queue_items,
        )

    async def get_capacity_status(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 200,
        assumed_replicas: int | None = None,
    ) -> IngestionCapacityStatusResponse:
        now = datetime.now(UTC)
        lookback_seconds = Decimal(max(lookback_minutes * 60, 1))
        resolved_replicas = max(
            assumed_replicas if assumed_replicas is not None else CAPACITY_ASSUMED_REPLICAS, 1
        )
        async for db in get_async_db_session():
            since = now - timedelta(minutes=lookback_minutes)
            rows = await db.execute(
                select(
                    DBIngestionJob.endpoint,
                    DBIngestionJob.entity_type,
                    func.sum(DBIngestionJob.accepted_count).label("total_records"),
                    func.sum(
                        case(
                            (
                                DBIngestionJob.status.in_(["queued", "failed"]),
                                DBIngestionJob.accepted_count,
                            ),
                            else_=0,
                        )
                    ).label("processed_records"),
                    func.sum(
                        case(
                            (DBIngestionJob.status == "accepted", DBIngestionJob.accepted_count),
                            else_=0,
                        )
                    ).label("backlog_records"),
                    func.sum(case((DBIngestionJob.status == "accepted", 1), else_=0)).label(
                        "backlog_jobs"
                    ),
                )
                .where(DBIngestionJob.submitted_at >= since)
                .group_by(DBIngestionJob.endpoint, DBIngestionJob.entity_type)
                .order_by(desc("backlog_records"), desc("total_records"))
                .limit(limit)
            )

            groups: list[IngestionCapacityGroupResponse] = []
            for (
                endpoint,
                entity_type,
                total_records_raw,
                processed_records_raw,
                backlog_records_raw,
                backlog_jobs_raw,
            ) in rows:
                groups.append(
                    _derive_capacity_group(
                        endpoint=str(endpoint),
                        entity_type=str(entity_type),
                        total_records=int(total_records_raw or 0),
                        processed_records=int(processed_records_raw or 0),
                        backlog_records=int(backlog_records_raw or 0),
                        backlog_jobs=int(backlog_jobs_raw or 0),
                        lookback_seconds=lookback_seconds,
                        assumed_replicas=resolved_replicas,
                    )
                )

            return IngestionCapacityStatusResponse(
                as_of=now,
                lookback_minutes=lookback_minutes,
                assumed_replicas=resolved_replicas,
                total_backlog_records=sum(item.backlog_records for item in groups),
                total_groups=len(groups),
                groups=groups,
            )

        return IngestionCapacityStatusResponse(
            as_of=now,
            lookback_minutes=lookback_minutes,
            assumed_replicas=resolved_replicas,
            total_backlog_records=0,
            total_groups=0,
            groups=[],
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
            total_backlog_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            and_(
                                DBIngestionJob.submitted_at >= since,
                                DBIngestionJob.status.in_(["accepted", "queued"]),
                            )
                        )
                    )
                )
                or 0
            )
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

            grouped_rows = rows.all()
            items: list[IngestionBacklogBreakdownItemResponse] = []
            for (
                endpoint,
                entity_type,
                total_jobs_raw,
                accepted_jobs_raw,
                queued_jobs_raw,
                failed_jobs_raw,
                oldest_backlog_submitted_at,
            ) in grouped_rows:
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
                items.append(
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

            items = sorted(
                items,
                key=lambda item: (item.backlog_jobs, item.oldest_backlog_age_seconds),
                reverse=True,
            )[:limit]

            largest_group_backlog_jobs = int(items[0].backlog_jobs if items else 0)
            if total_backlog_jobs > 0:
                largest_group_backlog_share = Decimal(largest_group_backlog_jobs) / Decimal(
                    total_backlog_jobs
                )
                top_3_backlog_jobs = int(sum(item.backlog_jobs for item in items[:3]))
                top_3_backlog_share = Decimal(top_3_backlog_jobs) / Decimal(total_backlog_jobs)
            else:
                largest_group_backlog_share = Decimal("0")
                top_3_backlog_share = Decimal("0")

            return IngestionBacklogBreakdownResponse(
                lookback_minutes=lookback_minutes,
                total_backlog_jobs=total_backlog_jobs,
                largest_group_backlog_jobs=largest_group_backlog_jobs,
                largest_group_backlog_share=largest_group_backlog_share,
                top_3_backlog_share=top_3_backlog_share,
                groups=items,
            )

        return IngestionBacklogBreakdownResponse(
            lookback_minutes=lookback_minutes,
            total_backlog_jobs=0,
            largest_group_backlog_jobs=0,
            largest_group_backlog_share=Decimal("0"),
            top_3_backlog_share=Decimal("0"),
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
                    else (
                        "Inspect downstream processing bottlenecks and verify queued "
                        "job drain progress."
                    )
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
                    DBConsumerDlqReplayAudit.replay_status.in_(
                        _SUCCESSFUL_REPLAY_AUDIT_STATUSES
                    ),
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
            if replay_status in _FAILED_REPLAY_AUDIT_STATUSES:
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
            try:
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
                dlq_events_in_window = int(
                    (
                        await db.execute(
                            select(func.count(DBConsumerDlqEvent.id)).where(
                                DBConsumerDlqEvent.observed_at >= current_since
                            )
                        )
                    ).scalar_one()
                    or 0
                )

                total_jobs = int(current_row[0] or 0)
                failed_jobs = int(current_row[1] or 0)
                failure_rate = (
                    Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
                )
                remaining_budget = max(Decimal("0"), failure_rate_threshold - failure_rate)
                backlog_jobs = int(current_row[2] or 0)
                previous_backlog_jobs = int(previous_row[0] or 0)
                backlog_growth = backlog_jobs - previous_backlog_jobs
                replay_backlog_pressure_ratio = Decimal(backlog_jobs) / Decimal(
                    max(1, REPLAY_MAX_BACKLOG_JOBS)
                )
                dlq_budget_events_per_window = max(1, DLQ_BUDGET_EVENTS_PER_WINDOW)
                dlq_pressure_ratio = Decimal(dlq_events_in_window) / Decimal(
                    dlq_budget_events_per_window
                )

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
                    replay_backlog_pressure_ratio=replay_backlog_pressure_ratio,
                    dlq_events_in_window=dlq_events_in_window,
                    dlq_budget_events_per_window=dlq_budget_events_per_window,
                    dlq_pressure_ratio=dlq_pressure_ratio,
                    breach_failure_rate=failure_rate > failure_rate_threshold,
                    breach_backlog_growth=backlog_growth > backlog_growth_threshold,
                )
            except SQLAlchemyError as exc:
                logger.warning(
                    "ingestion_error_budget_status_unavailable",
                    extra={"lookback_minutes": lookback_minutes},
                    exc_info=exc,
                )
                return self._default_error_budget_status(
                    lookback_minutes=lookback_minutes,
                    failure_rate_threshold=failure_rate_threshold,
                )
        return self._default_error_budget_status(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
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
        await self.assert_retry_allowed_for_records(
            submitted_at=submitted_at,
            replay_record_count=1,
        )

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
