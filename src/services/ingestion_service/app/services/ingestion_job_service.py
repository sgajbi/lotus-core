from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

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
from sqlalchemy import and_, case, desc, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from ..DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionBacklogBreakdownResponse,
    IngestionCapacityStatusResponse,
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
    IngestionSloStatusResponse,
    IngestionStalledJobListResponse,
    IngestionStalledJobResponse,
)
from ..settings import get_ingestion_service_settings
from . import ingestion_capacity_status as _capacity_status
from . import ingestion_error_budget_status as _error_budget_status
from .ingestion_backlog_breakdown import (
    build_backlog_breakdown_response,
    empty_backlog_breakdown_response,
)
from .ingestion_consumer_lag import load_consumer_lag_response
from .ingestion_job_listing import (
    IngestionJobListFilters,
    build_cursor_lookup_statement,
    build_ingestion_job_list_statement,
    ingestion_job_list_page,
)
from .ingestion_operating_band import (
    OperatingBandPolicy,
    OperatingBandSignals,
    classify_operating_band,
)
from .ingestion_record_status import (
    failed_record_keys_from_failures,
    replayable_record_keys_from_payload,
)
from .ingestion_replay_audits import (
    list_replay_audit_responses,
    to_replay_audit_response,
)
from .ingestion_reprocessing_queue_health import load_reprocessing_queue_health_response
from .ingestion_retry_guardrails import assert_replay_guardrails
from .ingestion_slo_status import (
    build_slo_status_response,
    load_ingestion_slo_snapshot,
)

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


OPERATING_BAND_POLICY = OperatingBandPolicy(
    yellow_backlog_age_seconds=_RUNTIME_POLICY.operating_band.yellow_backlog_age_seconds,
    orange_backlog_age_seconds=_RUNTIME_POLICY.operating_band.orange_backlog_age_seconds,
    red_backlog_age_seconds=_RUNTIME_POLICY.operating_band.red_backlog_age_seconds,
    yellow_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.yellow_dlq_pressure_ratio,
    orange_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.orange_dlq_pressure_ratio,
    red_dlq_pressure_ratio=_RUNTIME_POLICY.operating_band.red_dlq_pressure_ratio,
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


_SUCCESSFUL_REPLAY_AUDIT_STATUSES = {"replayed", "replayed_bookkeeping_failed"}
_FAILED_REPLAY_AUDIT_STATUSES = {"not_replayable", "failed", "replayed_bookkeeping_failed"}
_derive_capacity_group = _capacity_status._derive_capacity_group


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
        return _error_budget_status.default_error_budget_status(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            dlq_budget_events_per_window=DLQ_BUDGET_EVENTS_PER_WINDOW,
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

    async def record_failure_observation(
        self,
        job_id: str,
        failure_reason: str,
        *,
        failure_phase: str,
        failed_record_keys: list[str] | None = None,
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
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
            cursor_row = None
            if cursor is not None:
                cursor_row = await db.scalar(build_cursor_lookup_statement(cursor=cursor))
            stmt = build_ingestion_job_list_statement(
                filters=IngestionJobListFilters(
                    status=status,
                    entity_type=entity_type,
                    submitted_from=submitted_from,
                    submitted_to=submitted_to,
                ),
                cursor_row=cursor_row,
                limit=limit,
            )
            rows = list((await db.scalars(stmt)).all())
            page = ingestion_job_list_page(rows=rows, limit=limit)
            return ([_to_response(row) for row in page.rows], page.next_cursor)
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
            oldest_backlog_job_id = await db.scalar(
                select(DBIngestionJob.job_id)
                .where(DBIngestionJob.status.in_(("accepted", "queued")))
                .order_by(DBIngestionJob.submitted_at.asc(), DBIngestionJob.id.asc())
                .limit(1)
            )
            return IngestionHealthSummaryResponse(
                total_jobs=total_jobs,
                accepted_jobs=accepted_jobs,
                queued_jobs=queued_jobs,
                failed_jobs=failed_jobs,
                backlog_jobs=accepted_jobs + queued_jobs,
                oldest_backlog_job_id=oldest_backlog_job_id,
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
            now = datetime.now(UTC)
            since = now - timedelta(minutes=lookback_minutes)
            try:
                snapshot = await load_ingestion_slo_snapshot(
                    db,
                    since=since,
                    now=now,
                )
            except SQLAlchemyError as exc:
                logger.warning(
                    "ingestion_slo_status_fallback_unavailable",
                    extra={"lookback_minutes": lookback_minutes},
                    exc_info=exc,
                )
                return self._default_slo_status(lookback_minutes=lookback_minutes)
            INGESTION_BACKLOG_AGE_SECONDS.set(snapshot.backlog_age_seconds)
            return build_slo_status_response(
                lookback_minutes=lookback_minutes,
                snapshot=snapshot,
                failure_rate_threshold=failure_rate_threshold,
                queue_latency_threshold_seconds=queue_latency_threshold_seconds,
                backlog_age_threshold_seconds=backlog_age_threshold_seconds,
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
            ),
            policy=OPERATING_BAND_POLICY,
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
        return await load_reprocessing_queue_health_response(
            session_factory=get_async_db_session,
        )

    async def get_capacity_status(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 200,
        assumed_replicas: int | None = None,
    ) -> IngestionCapacityStatusResponse:
        return await _capacity_status.load_capacity_status_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            assumed_replicas=assumed_replicas,
            default_assumed_replicas=CAPACITY_ASSUMED_REPLICAS,
            session_factory=get_async_db_session,
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

            return build_backlog_breakdown_response(
                lookback_minutes=lookback_minutes,
                total_backlog_jobs=total_backlog_jobs,
                grouped_rows=list(rows.all()),
                now=now_utc,
                limit=limit,
            )

        return empty_backlog_breakdown_response(lookback_minutes=lookback_minutes)

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
                    DBConsumerDlqReplayAudit.replay_status.in_(_SUCCESSFUL_REPLAY_AUDIT_STATUSES),
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
            return to_replay_audit_response(row) if row else None
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
        return await list_replay_audit_responses(
            limit=limit,
            recovery_path=recovery_path,
            replay_status=replay_status,
            replay_fingerprint=replay_fingerprint,
            job_id=job_id,
            session_factory=get_async_db_session,
        )

    async def get_consumer_lag(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 100,
    ) -> IngestionConsumerLagResponse:
        return await load_consumer_lag_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            session_factory=get_async_db_session,
            health_summary_loader=self.get_health_summary,
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

            payload = row.request_payload if isinstance(row.request_payload, dict) else {}

            return IngestionJobRecordStatusResponse(
                job_id=row.job_id,
                entity_type=row.entity_type,
                accepted_count=row.accepted_count,
                failed_record_keys=failed_record_keys_from_failures(list(failures)),
                replayable_record_keys=replayable_record_keys_from_payload(
                    endpoint=row.endpoint,
                    payload=payload,
                ),
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
        return await _error_budget_status.load_error_budget_status_response(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            backlog_growth_threshold=backlog_growth_threshold,
            replay_max_backlog_jobs=REPLAY_MAX_BACKLOG_JOBS,
            dlq_budget_events_per_window=DLQ_BUDGET_EVENTS_PER_WINDOW,
            session_factory=get_async_db_session,
            logger=logger,
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
        now = datetime.now(UTC)
        backlog_jobs = await self._count_backlog_jobs()
        assert_replay_guardrails(
            mode=mode.mode,
            replay_window_start=mode.replay_window_start,
            replay_window_end=mode.replay_window_end,
            submitted_at=submitted_at,
            replay_record_count=replay_record_count,
            backlog_jobs=backlog_jobs,
            now=now,
            max_records_per_request=REPLAY_MAX_RECORDS_PER_REQUEST,
            max_backlog_jobs=REPLAY_MAX_BACKLOG_JOBS,
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
