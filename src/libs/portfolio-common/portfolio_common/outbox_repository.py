import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import OutboxEvent
from portfolio_common.logging_utils import normalize_lineage_value

logger = logging.getLogger(__name__)

EVENT_SCHEMA_VERSION = "1.0.0"
EVENT_ENVELOPE_FIELDS = ("event_type", "schema_version", "correlation_id")


class OutboxRepository:
    """
    Repository for creating and fetching OutboxEvent records.
    Stores payloads as native dicts so SQLAlchemy can serialize to JSON.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_outbox_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        topic: str,
        correlation_id: Optional[str] = None,
    ) -> OutboxEvent:
        """
        Create a new outbox event in PENDING status.
        - aggregate_id MUST be present (typically portfolio_id for partition affinity).
        - payload MUST be a dict; it will be stored directly in the JSON column.
        """
        if not aggregate_id:
            raise ValueError("aggregate_id (portfolio_id) is required for outbox events")

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict (will be serialized by SQLAlchemy JSON type)")

        correlation_id = normalize_lineage_value(correlation_id)

        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            status="PENDING",
            event_type=event_type,
            payload=build_outbox_payload(
                payload=payload,
                event_type=event_type,
                correlation_id=correlation_id,
            ),
            topic=topic,
            correlation_id=correlation_id,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()
        logger.info(
            "Outbox event created",
            extra={
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "topic": topic,
                "outbox_id": event.id,
            },
        )
        return event


def build_outbox_payload(
    *,
    payload: Dict[str, Any],
    event_type: str,
    correlation_id: Optional[str],
) -> Dict[str, Any]:
    """Return an auditable Kafka payload without mutating the caller-owned domain payload."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict (will be serialized by SQLAlchemy JSON type)")

    enriched_payload = dict(payload)
    normalized_correlation_id = normalize_lineage_value(correlation_id)
    _require_matching_payload_metadata(enriched_payload, "event_type", event_type)
    _require_matching_payload_metadata(enriched_payload, "schema_version", EVENT_SCHEMA_VERSION)
    if normalized_correlation_id is not None:
        _require_matching_payload_metadata(
            enriched_payload,
            "correlation_id",
            normalized_correlation_id,
        )

    enriched_payload["event_type"] = event_type
    enriched_payload["schema_version"] = EVENT_SCHEMA_VERSION
    enriched_payload["correlation_id"] = normalized_correlation_id
    return enriched_payload


def _require_matching_payload_metadata(
    payload: Dict[str, Any],
    field_name: str,
    expected_value: str,
) -> None:
    existing_raw_value = payload.get(field_name)
    existing_value = (
        normalize_lineage_value(str(existing_raw_value)) if existing_raw_value is not None else None
    )
    if existing_value is not None and existing_value != expected_value:
        raise ValueError(
            f"payload {field_name} {existing_value!r} does not match outbox "
            f"{field_name} {expected_value!r}"
        )
