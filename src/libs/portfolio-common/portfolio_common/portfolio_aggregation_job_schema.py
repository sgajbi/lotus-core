"""Database integrity and access paths owned by portfolio aggregation jobs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from .database_text_contract import PYTHON_STRIP_BOUNDARY_SQL


def portfolio_aggregation_job_table_args(*, correlation_id: Any) -> tuple[Any, ...]:
    """Return the aggregation job's tenant, lease, lineage, and access contract."""

    return (
        UniqueConstraint(
            "tenant_id",
            "portfolio_id",
            "aggregation_date",
            name="uq_portfolio_aggregation_jobs_tenant_portfolio_date",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_aggregation_jobs_tenant_portfolio",
        ),
        CheckConstraint(
            f"tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128",
            name="ck_portfolio_aggregation_jobs_tenant_normalized",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
            "lease_expires_at IS NOT NULL)",
            name="ck_portfolio_aggregation_jobs_lease_complete",
        ),
        CheckConstraint(
            "target_epoch >= 0",
            name="ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
        ),
        CheckConstraint(
            "source_revision >= 1",
            name="ck_portfolio_aggregation_jobs_source_revision_positive",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_aggregation_date",
            "status",
            "aggregation_date",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_status_lease_expiry",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_claim_order",
            "status",
            "portfolio_id",
            "aggregation_date",
            "id",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_portfolio_status_updated",
            "portfolio_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id",
            "portfolio_id",
            "status",
            "aggregation_date",
            "updated_at",
            "id",
        ),
        Index(
            "ix_agg_jobs_port_corr_date_updated_id",
            "portfolio_id",
            "correlation_id",
            "aggregation_date",
            "updated_at",
            "id",
            postgresql_where=correlation_id.is_not(None),
        ),
        Index(
            "ix_portfolio_aggregation_jobs_tenant_portfolio_status_date",
            "tenant_id",
            "portfolio_id",
            "status",
            "aggregation_date",
        ),
        Index("ix_portfolio_aggregation_jobs_alternate_lookup_key", "alternate_lookup_key"),
    )
