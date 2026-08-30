"""Tenant-owned simulation session persistence model."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
)

from .db_base import Base


class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(String(128), index=True, nullable=False)
    portfolio_id = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False, server_default="ACTIVE")
    version = Column(Integer, nullable=False, server_default="1")
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_simulation_sessions_tenant_portfolio",
        ),
        CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> ''",
            name="ck_simulation_sessions_tenant_authority",
        ),
        Index("ix_simulation_sessions_tenant_session_id", "tenant_id", "session_id"),
    )
