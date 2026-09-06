"""Database integrity and access paths owned by processed-event fences."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index


def processed_event_table_args(*, tenant_id: Any, semantic_key: Any) -> tuple[Any, ...]:
    """Return tenant-owned and deliberately global event-fence constraints."""

    return (
        CheckConstraint(
            "(service_name NOT IN ('persistence-transactions', "
            "'portfolio-transaction-processing', 'cashflow-calculator') "
            "OR tenant_id IS NOT NULL) AND (tenant_id IS NULL OR "
            "(tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND char_length(tenant_id) <= 128))",
            name="ck_processed_events_tenant_authority",
        ),
        Index(
            "uq_processed_events_tenant_event_service",
            "tenant_id",
            "event_id",
            "service_name",
            unique=True,
            postgresql_where=tenant_id.isnot(None),
            sqlite_where=tenant_id.isnot(None),
        ),
        Index(
            "uq_processed_events_global_event_service",
            "event_id",
            "service_name",
            unique=True,
            postgresql_where=tenant_id.is_(None),
            sqlite_where=tenant_id.is_(None),
        ),
        Index("ix_processed_events_alternate_lookup_key", "alternate_lookup_key"),
        Index(
            "uq_processed_events_tenant_service_semantic_key",
            "tenant_id",
            "service_name",
            "semantic_key",
            unique=True,
            postgresql_where=tenant_id.isnot(None) & semantic_key.isnot(None),
            sqlite_where=tenant_id.isnot(None) & semantic_key.isnot(None),
        ),
        Index(
            "uq_processed_events_global_service_semantic_key",
            "service_name",
            "semantic_key",
            unique=True,
            postgresql_where=tenant_id.is_(None) & semantic_key.isnot(None),
            sqlite_where=tenant_id.is_(None) & semantic_key.isnot(None),
        ),
    )
