from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from portfolio_common.database_models import ConsumerDlqEvent as DBConsumerDlqEvent
from sqlalchemy import desc, func, select

from ..DTOs.ingestion_job_dto import (
    IngestionConsumerLagGroupResponse,
    IngestionConsumerLagResponse,
    IngestionHealthSummaryResponse,
)


def classify_consumer_lag_severity(
    dlq_events: int,
) -> Literal["low", "medium", "high"]:
    if dlq_events >= 20:
        return "high"
    if dlq_events >= 5:
        return "medium"
    return "low"


async def load_consumer_lag_response(
    *,
    lookback_minutes: int,
    limit: int,
    session_factory,
    health_summary_loader: Callable[[], Awaitable[IngestionHealthSummaryResponse]],
) -> IngestionConsumerLagResponse:
    async for db in session_factory():
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
            groups.append(
                IngestionConsumerLagGroupResponse(
                    consumer_group=consumer_group,
                    original_topic=original_topic,
                    dlq_events=dlq_events,
                    last_observed_at=last_observed_at,
                    lag_severity=classify_consumer_lag_severity(dlq_events),
                )
            )
        backlog = await health_summary_loader()
        return build_consumer_lag_response(
            lookback_minutes=lookback_minutes,
            backlog=backlog,
            groups=groups,
        )

    return IngestionConsumerLagResponse(
        lookback_minutes=lookback_minutes,
        backlog_jobs=0,
        total_groups=0,
        groups=[],
    )


def build_consumer_lag_response(
    *,
    lookback_minutes: int,
    backlog: IngestionHealthSummaryResponse,
    groups: list[IngestionConsumerLagGroupResponse],
) -> IngestionConsumerLagResponse:
    return IngestionConsumerLagResponse(
        lookback_minutes=lookback_minutes,
        backlog_jobs=backlog.backlog_jobs,
        total_groups=len(groups),
        groups=groups,
    )
