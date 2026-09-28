"""Table-level integrity and access-path schema for financial reconciliation."""

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, text

from .database_text_contract import PYTHON_STRIP_BOUNDARY_SQL


def financial_reconciliation_run_table_args(*, row_id: Any, started_at: Any) -> tuple[Any, ...]:
    """Build durable tenant authority and query indexes for reconciliation runs."""

    return (
        UniqueConstraint(
            "authority_scope",
            "tenant_id",
            "run_id",
            name="uq_fin_recon_runs_authority_run",
        ),
        UniqueConstraint(
            "authority_scope",
            "run_id",
            name="uq_fin_recon_runs_scope_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_fin_recon_runs_tenant_portfolio",
        ),
        CheckConstraint(
            "(authority_scope = 'TENANT' AND tenant_id IS NOT NULL "
            f"AND tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128) "
            "OR (authority_scope = 'ESTATE' AND tenant_id IS NULL AND portfolio_id IS NULL)",
            name="ck_fin_recon_runs_authority_scope",
        ),
        CheckConstraint(
            "aggregation_revision IS NULL OR aggregation_revision >= 0",
            name="ck_fin_recon_aggregation_revision_nonnegative",
        ),
        Index(
            "ix_fin_recon_scope_revision_type",
            "tenant_id",
            "portfolio_id",
            "business_date",
            "epoch",
            "aggregation_revision",
            "reconciliation_type",
        ),
        Index(
            "ix_fin_recon_runs_tenant_type_status_started",
            "tenant_id",
            "reconciliation_type",
            "status",
            started_at.desc(),
        ),
        Index(
            "ix_fin_recon_runs_tenant_port_status_started",
            "tenant_id",
            "portfolio_id",
            "status",
            started_at.desc(),
            row_id.asc(),
        ),
        Index(
            "ix_fin_recon_runs_tenant_port_type_started",
            "tenant_id",
            "portfolio_id",
            "reconciliation_type",
            started_at.desc(),
            row_id.desc(),
        ),
        Index(
            "ix_fin_recon_runs_tenant_port_corr_started",
            "tenant_id",
            "portfolio_id",
            "correlation_id",
            started_at.desc(),
            row_id.asc(),
        ),
        Index(
            "ix_fin_recon_runs_tenant_port_requester_started",
            "tenant_id",
            "portfolio_id",
            "requested_by",
            started_at.desc(),
            row_id.asc(),
        ),
        Index(
            "ix_fin_recon_runs_tenant_port_date_epoch_started",
            "tenant_id",
            "portfolio_id",
            "business_date",
            "epoch",
            started_at.desc(),
            row_id.desc(),
        ),
        Index(
            "uq_fin_recon_runs_tenant_dedupe",
            "tenant_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("authority_scope = 'TENANT' AND dedupe_key IS NOT NULL"),
            sqlite_where=text("authority_scope = 'TENANT' AND dedupe_key IS NOT NULL"),
        ),
    )


def financial_reconciliation_finding_table_args(
    *,
    row_id: Any,
    created_at: Any,
) -> tuple[Any, ...]:
    """Build durable tenant authority and query indexes for reconciliation findings."""

    return (
        ForeignKeyConstraint(
            ["authority_scope", "run_id"],
            [
                "financial_reconciliation_runs.authority_scope",
                "financial_reconciliation_runs.run_id",
            ],
            name="fk_fin_recon_findings_scope_run",
        ),
        ForeignKeyConstraint(
            ["authority_scope", "tenant_id", "run_id"],
            [
                "financial_reconciliation_runs.authority_scope",
                "financial_reconciliation_runs.tenant_id",
                "financial_reconciliation_runs.run_id",
            ],
            name="fk_fin_recon_findings_authority_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_fin_recon_findings_tenant_portfolio",
        ),
        CheckConstraint(
            "(authority_scope = 'TENANT' AND tenant_id IS NOT NULL "
            f"AND tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128) "
            "OR (authority_scope = 'ESTATE' AND tenant_id IS NULL)",
            name="ck_fin_recon_findings_authority_scope",
        ),
        CheckConstraint("btrim(owner) <> ''", name="ck_fin_recon_finding_owner_nonempty"),
        CheckConstraint(
            "resolution_state IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'WAIVED', 'SUPPRESSED')",
            name="ck_fin_recon_finding_resolution_state",
        ),
        CheckConstraint(
            "(resolution_state IN ('OPEN', 'IN_PROGRESS') "
            "AND resolution_actor IS NULL AND resolved_at IS NULL) OR ("
            "resolution_state IN ('RESOLVED', 'WAIVED', 'SUPPRESSED') "
            "AND resolution_actor IS NOT NULL AND btrim(resolution_actor) <> '' "
            "AND resolved_at IS NOT NULL AND resolved_at >= created_at)",
            name="ck_fin_recon_finding_resolution_evidence",
        ),
        CheckConstraint(
            "btrim(repair_recommendation) <> ''",
            name="ck_fin_recon_finding_repair_nonempty",
        ),
        Index(
            "ix_fin_recon_findings_tenant_run_severity_type",
            "tenant_id",
            "run_id",
            "severity",
            "finding_type",
            row_id.asc(),
        ),
        Index(
            "ix_fin_recon_findings_tenant_run_severity_created",
            "tenant_id",
            "run_id",
            "severity",
            created_at.desc(),
            row_id.desc(),
        ),
        Index(
            "ix_fin_recon_findings_tenant_run_resolution_created",
            "tenant_id",
            "run_id",
            "resolution_state",
            "severity",
            created_at.asc(),
            row_id.asc(),
        ),
    )


__all__ = [
    "financial_reconciliation_finding_table_args",
    "financial_reconciliation_run_table_args",
]
