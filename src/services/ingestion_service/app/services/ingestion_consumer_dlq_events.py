from __future__ import annotations

from portfolio_common.database_models import (
    ConsumerDlqEvent as DBConsumerDlqEvent,
)
from portfolio_common.database_models import (
    IngestionJob as DBIngestionJob,
)
from sqlalchemy import desc, select

from ..DTOs.ingestion_job_dto import ConsumerDlqEventResponse


def _missing_correlation_reason(event: DBConsumerDlqEvent) -> str | None:
    reason = getattr(event, "correlation_missing_reason", None)
    if reason:
        return reason
    if event.correlation_id:
        return None
    return "message_correlation_id_absent"


def _alternate_lookup_key(event: DBConsumerDlqEvent) -> str | None:
    lookup_key = getattr(event, "alternate_lookup_key", None)
    if lookup_key:
        return lookup_key
    if event.correlation_id:
        return None
    original_key = event.original_key or "unkeyed"
    return (
        f"consumer_dlq|topic={event.original_topic}|group={event.consumer_group}|"
        f"dlq={event.dlq_topic}|key={original_key}|event={event.event_id}"
    )


def to_consumer_dlq_event_response(event: DBConsumerDlqEvent) -> ConsumerDlqEventResponse:
    return ConsumerDlqEventResponse(
        event_id=event.event_id,
        original_topic=event.original_topic,
        consumer_group=event.consumer_group,
        dlq_topic=event.dlq_topic,
        original_key=event.original_key,
        error_reason_code=event.error_reason_code,
        error_reason=event.error_reason,
        correlation_id=event.correlation_id,
        ingestion_job_id=getattr(event, "ingestion_job_id", None),
        correlation_missing_reason=_missing_correlation_reason(event),
        alternate_lookup_key=_alternate_lookup_key(event),
        payload_excerpt=event.payload_excerpt,
        observed_at=event.observed_at,
    )


async def list_consumer_dlq_event_responses(
    *,
    tenant_id: str,
    limit: int,
    original_topic: str | None,
    consumer_group: str | None,
    session_factory,
    ingestion_job_id: str | None = None,
    event_ids: tuple[str, ...] | None = None,
) -> list[ConsumerDlqEventResponse]:
    async for db in session_factory():
        stmt = (
            select(DBConsumerDlqEvent)
            .join(
                DBIngestionJob,
                DBIngestionJob.job_id == DBConsumerDlqEvent.ingestion_job_id,
            )
            .where(DBIngestionJob.tenant_id == tenant_id)
        )
        if original_topic:
            stmt = stmt.where(DBConsumerDlqEvent.original_topic == original_topic)
        if consumer_group:
            stmt = stmt.where(DBConsumerDlqEvent.consumer_group == consumer_group)
        if ingestion_job_id:
            stmt = stmt.where(DBConsumerDlqEvent.ingestion_job_id == ingestion_job_id)
        if event_ids:
            stmt = stmt.where(DBConsumerDlqEvent.event_id.in_(event_ids))
        rows = (
            await db.scalars(
                stmt.order_by(
                    desc(DBConsumerDlqEvent.observed_at),
                    desc(DBConsumerDlqEvent.id),
                ).limit(limit)
            )
        ).all()
        return [to_consumer_dlq_event_response(row) for row in rows]
    return []


async def get_consumer_dlq_event_response(
    *,
    tenant_id: str,
    event_id: str,
    session_factory,
) -> ConsumerDlqEventResponse | None:
    async for db in session_factory():
        row = await db.scalar(
            select(DBConsumerDlqEvent)
            .join(
                DBIngestionJob,
                DBIngestionJob.job_id == DBConsumerDlqEvent.ingestion_job_id,
            )
            .where(
                DBIngestionJob.tenant_id == tenant_id,
                DBConsumerDlqEvent.event_id == event_id,
            )
            .limit(1)
        )
        return to_consumer_dlq_event_response(row) if row else None
    return None
