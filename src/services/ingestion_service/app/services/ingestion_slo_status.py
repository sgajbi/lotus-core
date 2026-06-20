from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError

from ..DTOs.ingestion_job_dto import IngestionSloStatusResponse


@dataclass(frozen=True, slots=True)
class IngestionSloSnapshot:
    total_jobs: int
    failed_jobs: int
    p95_latency_seconds: float
    backlog_age_seconds: float


def default_slo_status(*, lookback_minutes: int) -> IngestionSloStatusResponse:
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


async def load_slo_status_response(
    *,
    lookback_minutes: int,
    failure_rate_threshold: Decimal,
    queue_latency_threshold_seconds: float,
    backlog_age_threshold_seconds: float,
    session_factory,
    backlog_age_metric,
    logger,
) -> IngestionSloStatusResponse:
    async for db in session_factory():
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
            return default_slo_status(lookback_minutes=lookback_minutes)
        backlog_age_metric.set(snapshot.backlog_age_seconds)
        return build_slo_status_response(
            lookback_minutes=lookback_minutes,
            snapshot=snapshot,
            failure_rate_threshold=failure_rate_threshold,
            queue_latency_threshold_seconds=queue_latency_threshold_seconds,
            backlog_age_threshold_seconds=backlog_age_threshold_seconds,
        )
    return default_slo_status(lookback_minutes=lookback_minutes)


def _latency_seconds_expression() -> Any:
    return case(
        (
            DBIngestionJob.completed_at.is_not(None),
            func.extract(
                "epoch",
                DBIngestionJob.completed_at - DBIngestionJob.submitted_at,
            ),
        ),
        else_=None,
    )


async def load_ingestion_slo_snapshot(
    db: Any,
    *,
    since: datetime,
    now: datetime,
) -> IngestionSloSnapshot:
    try:
        return await _load_aggregate_slo_snapshot(db, since=since, now=now)
    except SQLAlchemyError:
        return await _load_fallback_slo_snapshot(db, since=since, now=now)


async def _load_aggregate_slo_snapshot(
    db: Any,
    *,
    since: datetime,
    now: datetime,
) -> IngestionSloSnapshot:
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
                .within_group(_latency_seconds_expression())
                .label("p95_latency"),
            ).where(DBIngestionJob.submitted_at >= since)
        )
    ).one()
    total_jobs = int(row[0] or 0)
    failed_jobs = int(row[1] or 0)
    oldest_backlog_submitted_at = row[2]
    p95_latency = float(row[3] or 0.0)
    backlog_age_seconds = _backlog_age_seconds(
        oldest_submitted_at=oldest_backlog_submitted_at,
        now=now,
    )
    return IngestionSloSnapshot(
        total_jobs=total_jobs,
        failed_jobs=failed_jobs,
        p95_latency_seconds=p95_latency,
        backlog_age_seconds=backlog_age_seconds,
    )


async def _load_fallback_slo_snapshot(
    db: Any,
    *,
    since: datetime,
    now: datetime,
) -> IngestionSloSnapshot:
    jobs = (
        await db.scalars(select(DBIngestionJob).where(DBIngestionJob.submitted_at >= since))
    ).all()
    return slo_snapshot_from_jobs(jobs=list(jobs), now=now)


def slo_snapshot_from_jobs(
    *,
    jobs: list[Any],
    now: datetime,
) -> IngestionSloSnapshot:
    latencies = sorted(
        (job.completed_at - job.submitted_at).total_seconds()
        for job in jobs
        if job.completed_at is not None
    )
    non_terminal_submitted_at = [
        job.submitted_at for job in jobs if job.status in {"accepted", "queued"}
    ]
    return IngestionSloSnapshot(
        total_jobs=len(jobs),
        failed_jobs=sum(1 for job in jobs if job.status == "failed"),
        p95_latency_seconds=_p95_latency_seconds(latencies),
        backlog_age_seconds=_backlog_age_seconds(
            oldest_submitted_at=min(non_terminal_submitted_at, default=None),
            now=now,
        ),
    )


def build_slo_status_response(
    *,
    lookback_minutes: int,
    snapshot: IngestionSloSnapshot,
    failure_rate_threshold: Decimal,
    queue_latency_threshold_seconds: float,
    backlog_age_threshold_seconds: float,
) -> IngestionSloStatusResponse:
    failure_rate = (
        Decimal(snapshot.failed_jobs) / Decimal(snapshot.total_jobs)
        if snapshot.total_jobs
        else Decimal("0")
    )
    return IngestionSloStatusResponse(
        lookback_minutes=lookback_minutes,
        total_jobs=snapshot.total_jobs,
        failed_jobs=snapshot.failed_jobs,
        failure_rate=failure_rate,
        p95_queue_latency_seconds=snapshot.p95_latency_seconds,
        backlog_age_seconds=snapshot.backlog_age_seconds,
        breach_failure_rate=failure_rate > failure_rate_threshold,
        breach_queue_latency=snapshot.p95_latency_seconds > queue_latency_threshold_seconds,
        breach_backlog_age=snapshot.backlog_age_seconds > backlog_age_threshold_seconds,
    )


def _p95_latency_seconds(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    return latencies[p95_index]


def _backlog_age_seconds(
    *,
    oldest_submitted_at: datetime | None,
    now: datetime,
) -> float:
    if oldest_submitted_at is None:
        return 0.0
    return (now - oldest_submitted_at).total_seconds()
