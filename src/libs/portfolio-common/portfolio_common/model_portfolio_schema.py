"""Owning schema for imported model definitions and targets."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)

from .db_base import Base


class ModelPortfolioDefinition(Base):
    __tablename__ = "model_portfolio_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_portfolio_id = Column(String, nullable=False, index=True)
    model_portfolio_version = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    base_currency = Column(String(3), nullable=False)
    risk_profile = Column(String, nullable=False)
    mandate_type = Column(String, nullable=False)
    rebalance_frequency = Column(String, nullable=True)
    approval_status = Column(String, nullable=False, server_default="approved", index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_model_portfolio_definition_effective_window",
        ),
        UniqueConstraint(
            "model_portfolio_id",
            "model_portfolio_version",
            "effective_from",
            name="_model_portfolio_definition_version_effective_uc",
        ),
        Index(
            "ix_model_portfolio_definition_effective_window",
            "model_portfolio_id",
            "effective_from",
            "effective_to",
        ),
        Index(
            "ix_model_port_def_approved_eff_order",
            "model_portfolio_id",
            effective_from.desc(),
            "effective_to",
            approved_at.desc(),
            updated_at.desc(),
            postgresql_where=text("approval_status = 'approved'"),
        ),
    )


def model_portfolio_target_window_constraint() -> CheckConstraint:
    """Keep target window integrity beside the owning model definition schema."""
    return CheckConstraint(
        "effective_to IS NULL OR effective_to >= effective_from",
        name="ck_model_portfolio_target_effective_window",
    )
