"""Database constraints and indexes for tenant-owned analytics export jobs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.elements import ColumnElement

from .database_text_contract import CANONICAL_TENANT_ID_CHECK_SQL


def analytics_export_job_table_args(id_column: ColumnElement[Any]) -> tuple[SchemaItem, ...]:
    return (
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_analytics_export_jobs_tenant_portfolio",
        ),
        CheckConstraint(
            CANONICAL_TENANT_ID_CHECK_SQL,
            name="ck_analytics_export_jobs_tenant_authority",
        ),
        Index(
            "ix_analytics_export_jobs_tenant_portfolio_status_created_at",
            "tenant_id",
            "portfolio_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_analytics_export_jobs_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_analytics_export_jobs_tenant_dataset_fingerprint_id",
            "tenant_id",
            "dataset_type",
            "request_fingerprint",
            id_column.desc(),
        ),
    )
