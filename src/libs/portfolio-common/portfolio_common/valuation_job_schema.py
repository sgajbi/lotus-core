"""Database integrity and access paths owned by portfolio valuation jobs."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, func

from .database_text_contract import PYTHON_STRIP_BOUNDARY_SQL


def portfolio_valuation_job_table_args(
    *,
    portfolio_id: Any,
    security_id: Any,
    valuation_date: Any,
    epoch: Any,
    status: Any,
    job_id: Any,
    correlation_id: Any,
) -> tuple:
    return (
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_valuation_jobs_tenant_portfolio",
        ),
        CheckConstraint(
            f"tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128",
            name="ck_portfolio_valuation_jobs_tenant_normalized",
        ),
        CheckConstraint(
            "valuation_claim_token IS NULL OR valuation_claim_token ~ '^[0-9a-f]{32}$'",
            name="ck_portfolio_valuation_jobs_claim_token",
        ),
        CheckConstraint(
            "(valuation_lease_owner IS NULL AND valuation_claim_token IS NULL "
            "AND valuation_lease_expires_at IS NULL) OR "
            "(valuation_lease_owner IS NOT NULL AND valuation_claim_token IS NOT NULL "
            "AND valuation_lease_expires_at IS NOT NULL)",
            name="ck_portfolio_valuation_jobs_lease_all_or_none",
        ),
        CheckConstraint(
            "valuation_lease_owner IS NULL OR btrim(valuation_lease_owner) <> ''",
            name="ck_portfolio_valuation_jobs_lease_owner_nonblank",
        ),
        CheckConstraint(
            "valuation_lease_expires_at IS NULL OR valuation_lease_expires_at "
            "NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
            name="ck_portfolio_valuation_jobs_lease_expiry_finite",
        ),
        CheckConstraint(
            "(status = 'PROCESSING' AND valuation_lease_owner IS NOT NULL "
            "AND valuation_claim_token IS NOT NULL AND valuation_lease_expires_at IS NOT NULL) "
            "OR (status <> 'PROCESSING' AND valuation_lease_owner IS NULL "
            "AND valuation_claim_token IS NULL AND valuation_lease_expires_at IS NULL)",
            name="ck_portfolio_valuation_jobs_processing_lease_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "portfolio_id",
            "security_id",
            "valuation_date",
            "epoch",
            name="uq_portfolio_valuation_jobs_tenant_scope_epoch",
        ),
        Index(
            "ix_portfolio_valuation_jobs_status_valuation_date",
            "status",
            "valuation_date",
        ),
        Index(
            "ix_portfolio_valuation_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_valuation_jobs_processing_lease_recovery",
            "valuation_lease_expires_at",
            "id",
            postgresql_where=status == "PROCESSING",
        ),
        Index(
            "ix_portfolio_valuation_jobs_claim_order_epoch",
            "status",
            "portfolio_id",
            "security_id",
            "valuation_date",
            epoch.desc(),
            "id",
        ),
        Index(
            "ix_portfolio_valuation_jobs_portfolio_status_updated",
            "portfolio_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id",
            "portfolio_id",
            "status",
            "valuation_date",
            "updated_at",
            "id",
        ),
        Index(
            "ix_val_jobs_norm_port_sec_date_epoch_status",
            func.trim(portfolio_id),
            func.trim(security_id),
            "valuation_date",
            "epoch",
            "status",
        ),
        Index(
            "ix_val_jobs_lineage_latest",
            "portfolio_id",
            func.trim(security_id),
            "epoch",
            valuation_date.desc(),
            job_id.desc(),
        ),
        Index(
            "ix_val_jobs_port_corr_date_updated_id",
            "portfolio_id",
            "correlation_id",
            "valuation_date",
            "updated_at",
            "id",
            postgresql_where=correlation_id.is_not(None),
        ),
        Index("ix_portfolio_valuation_jobs_alternate_lookup_key", "alternate_lookup_key"),
    )
