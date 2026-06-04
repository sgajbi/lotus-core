from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from portfolio_common.database_models import IngestionJob as DBIngestionJob
from sqlalchemy import case, desc, func, select

from ..DTOs.ingestion_job_dto import (
    IngestionCapacityGroupResponse,
    IngestionCapacityStatusResponse,
)


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


async def load_capacity_status_response(
    *,
    lookback_minutes: int,
    limit: int,
    assumed_replicas: int | None,
    default_assumed_replicas: int,
    session_factory,
) -> IngestionCapacityStatusResponse:
    now = datetime.now(UTC)
    lookback_seconds = Decimal(max(lookback_minutes * 60, 1))
    resolved_replicas = max(
        assumed_replicas if assumed_replicas is not None else default_assumed_replicas, 1
    )
    async for db in session_factory():
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
