"""Database access paths owned by durable outbox events."""

from typing import Any

from sqlalchemy import Index


def outbox_event_table_args(
    *, status: Any, payload: Any, aggregate_type: Any, event_type: Any
) -> tuple[Index, ...]:
    """Build independent indexes from the owning model's column expressions."""
    return (
        Index("ix_outbox_events_status_created_at", "status", "created_at"),
        Index("ix_outbox_events_status_last_attempted_at", "status", "last_attempted_at"),
        Index(
            "ix_outbox_events_status_next_attempt_created_at",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_outbox_events_status_claim_next_attempt_created_at",
            "status",
            "claim_expires_at",
            "next_attempt_at",
            "created_at",
        ),
        Index("ix_outbox_events_claim_token", "claim_token"),
        Index("ix_outbox_events_status_last_failure_at", "status", "last_failure_at"),
        Index(
            "ix_outbox_events_stream_unresolved_order",
            "topic",
            "partition_key",
            "created_at",
            "id",
            postgresql_where=status.in_(("PENDING", "FAILED")),
        ),
        Index("ix_outbox_events_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "ix_outbox_events_raw_transaction_source",
            "aggregate_id",
            payload["transaction_id"].as_string(),
            "id",
            postgresql_where=(aggregate_type == "RawTransaction")
            & (event_type == "RawTransactionPersisted"),
        ),
    )
