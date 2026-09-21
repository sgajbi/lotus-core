"""Database integrity and access paths owned by portfolio aggregation jobs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from .database_text_contract import PYTHON_STRIP_BOUNDARY_SQL
from .db_base import Base


def selected_history_lookup_index(
    portfolio_id: Any,
    security_id: Any,
    position_date: Any,
    history_id: Any,
) -> Index:
    """Index the exact legacy-aware lookup used by historical job promotion."""

    return Index(
        "ix_position_history_portfolio_strip_security_date_id",
        portfolio_id,
        func.btrim(security_id, text(PYTHON_STRIP_BOUNDARY_SQL)),
        position_date.desc(),
        history_id.desc(),
    )


class PortfolioSelectedHistoryObservation(Base):
    """Last selected source fact per security and affected aggregation boundary."""

    __tablename__ = "portfolio_selected_history_observations"

    tenant_id = Column(String(128), nullable=False)
    portfolio_id = Column(String, nullable=False)
    as_of_date = Column(Date, nullable=False)
    security_id = Column(String, nullable=False)
    position_history_id = Column(Integer, nullable=True)
    selected_business_date = Column(Date, nullable=True)
    selected_nonzero = Column(Boolean, nullable=False)
    source_fact = Column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "portfolio_id",
            "as_of_date",
            "security_id",
            name="pk_portfolio_selected_history_observations",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_selected_history_observations_tenant_portfolio",
        ),
        CheckConstraint(
            f"tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128 "
            "AND security_id = btrim(security_id, "
            f"{PYTHON_STRIP_BOUNDARY_SQL}) AND security_id <> ''",
            name="ck_portfolio_selected_history_observations_scope",
        ),
        CheckConstraint(
            "(position_history_id IS NULL AND selected_business_date IS NULL "
            "AND source_fact IS NULL AND NOT selected_nonzero) OR "
            "(position_history_id IS NOT NULL AND selected_business_date IS NOT NULL "
            "AND source_fact IS NOT NULL)",
            name="ck_portfolio_selected_history_observations_fact_complete",
        ),
        Index(
            "ix_portfolio_selected_history_observations_fact",
            "tenant_id",
            "portfolio_id",
            "security_id",
            "position_history_id",
            "selected_business_date",
        ),
    )


class PortfolioSelectedHistoryValuationState(Base):
    """Latest durable valuation outcome for one exact selected history fact."""

    __tablename__ = "portfolio_selected_history_valuation_states"

    tenant_id = Column(String(128), nullable=False)
    portfolio_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    position_history_id = Column(Integer, nullable=False)
    selected_business_date = Column(Date, nullable=False)
    source_fact = Column(Text, nullable=False)
    valuation_outcome = Column(String(16), nullable=False)
    valuation_epoch = Column(Integer, nullable=False)
    valuation_date = Column(Date, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "tenant_id",
            "portfolio_id",
            "security_id",
            "position_history_id",
            name="pk_portfolio_selected_history_valuation_states",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_portfolio_selected_history_valuation_states_tenant_portfolio",
        ),
        CheckConstraint(
            f"tenant_id = btrim(tenant_id, {PYTHON_STRIP_BOUNDARY_SQL}) "
            "AND tenant_id <> '' AND char_length(tenant_id) <= 128 "
            "AND security_id = btrim(security_id, "
            f"{PYTHON_STRIP_BOUNDARY_SQL}) AND security_id <> ''",
            name="ck_portfolio_selected_history_valuation_states_scope",
        ),
        CheckConstraint(
            "valuation_outcome IN ('READY', 'UNAVAILABLE')",
            name="ck_portfolio_selected_history_valuation_states_outcome",
        ),
        CheckConstraint(
            "valuation_epoch >= 0",
            name="ck_portfolio_selected_history_valuation_states_epoch",
        ),
    )


class PortfolioAggregationJobSweepMixin:
    """Durable per-day sweep state, kept with the aggregation job schema."""

    selected_history_sweep_epoch = Column(Integer, nullable=False, default=-1, server_default="-1")
    selected_history_collective_epoch = Column(
        Integer, nullable=False, default=0, server_default="0"
    )


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
        CheckConstraint(
            "selected_history_sweep_epoch >= -1",
            name="ck_portfolio_aggregation_jobs_selected_history_sweep_epoch",
        ),
        CheckConstraint(
            "selected_history_collective_epoch >= 0",
            name="ck_portfolio_aggregation_jobs_selected_history_collective_epoch",
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
