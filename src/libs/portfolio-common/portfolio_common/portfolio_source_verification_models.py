"""Append-only attestations linked to original facts, not another economic ledger."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB

from .db_base import Base
from .portfolio_source_observation_models import SOURCE_IDENTITY_COLUMNS


class PortfolioSourceVerificationRow(Base):
    __tablename__ = "portfolio_source_fact_verifications"

    attestation_sha256 = Column(String(64), primary_key=True)
    tenant_id = Column(String(128), nullable=False)
    portfolio_id = Column(String, nullable=False)
    producer_id = Column(String(128), nullable=False)
    source_record_id = Column(String(128), nullable=False)
    content_hash = Column(String(64), nullable=False)
    cash_observation_id = Column(String(64), nullable=True)
    funding_observation_id = Column(String(64), nullable=True)
    consumer_id = Column(String(128), nullable=False)
    receipt = Column(JSONB, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        *(
            ForeignKeyConstraint(
                [*SOURCE_IDENTITY_COLUMNS, column, "content_hash"],
                [
                    f"{table}.{name}"
                    for name in (*SOURCE_IDENTITY_COLUMNS, "observation_id", "content_hash")
                ],
            )
            for column, table in (
                ("cash_observation_id", "portfolio_cash_availability_observations"),
                ("funding_observation_id", "portfolio_funding_investment_observations"),
            )
        ),
        CheckConstraint("(cash_observation_id IS NULL) <> (funding_observation_id IS NULL)"),
        CheckConstraint("coalesce(cash_observation_id, funding_observation_id) = content_hash"),
        CheckConstraint("attestation_sha256 ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("jsonb_typeof(receipt) = 'object'"),
        CheckConstraint("isfinite(received_at)"),
        Index(
            "ix_source_fact_verification_custody",
            "tenant_id",
            "portfolio_id",
            "content_hash",
            "consumer_id",
        ),
    )
