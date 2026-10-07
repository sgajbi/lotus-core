"""Immutable source observations and separate, tenant-scoped current-head projections."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declared_attr

from .db_base import Base
from .domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationConflict,
    ObservationCoverage,
    ObservationEnvelope,
    PortfolioSourceObservation,
)
from .financial_numeric import ExactNumeric, finite_numeric_check_constraint

SOURCE_IDENTITY_COLUMNS = ("tenant_id", "portfolio_id", "producer_id", "source_record_id")


class ObservationColumns:
    """Receipt time and admission are server facts, not producer qualification."""

    observation_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(128), nullable=False)
    portfolio_id = Column(String, nullable=False)
    producer_id = Column(String(128), nullable=False)
    source_record_id = Column(String(128), nullable=False)
    source_revision = Column(BigInteger, nullable=False)
    source_cut_id = Column(String(128), nullable=False)
    definition_version = Column(String(128), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    coverage = Column(String(16), nullable=False)
    coverage_scope = Column(String(128), nullable=False)
    predecessor_id = Column(String(64), nullable=True)
    expected_head_hash = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=False)
    receipt_job_id = Column(String, nullable=False)
    admission_policy_version = Column(String(128), nullable=False)
    qualification = Column(String(16), nullable=False)

    @declared_attr
    def __table_args__(cls):
        table = cls.__tablename__
        return (
            UniqueConstraint(*SOURCE_IDENTITY_COLUMNS, "source_revision"),
            UniqueConstraint(*SOURCE_IDENTITY_COLUMNS, "observation_id", "content_hash"),
            ForeignKeyConstraint(
                ["tenant_id", "portfolio_id"],
                ["portfolios.tenant_id", "portfolios.portfolio_id"],
            ),
            ForeignKeyConstraint(
                ["tenant_id", "receipt_job_id"],
                ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"],
            ),
            ForeignKeyConstraint(
                [*SOURCE_IDENTITY_COLUMNS, "predecessor_id", "expected_head_hash"],
                [
                    f"{table}.{name}"
                    for name in (*SOURCE_IDENTITY_COLUMNS, "observation_id", "content_hash")
                ],
            ),
            CheckConstraint("source_revision > 0"),
            CheckConstraint("effective_to IS NULL OR effective_to > effective_from"),
            CheckConstraint("generated_at >= observed_at"),
            CheckConstraint("coverage IN ('complete', 'partial', 'missing')"),
            CheckConstraint("qualification = 'unqualified'"),
            CheckConstraint("observation_id = content_hash"),
            CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'"),
            CheckConstraint(
                "(source_revision = 1 AND predecessor_id IS NULL AND expected_head_hash IS NULL) "
                "OR (source_revision > 1 AND predecessor_id IS NOT NULL "
                "AND expected_head_hash IS NOT NULL)"
            ),
            *cls.family_constraints(),
        )


class CashAvailabilityObservationRow(ObservationColumns, Base):
    __tablename__ = "portfolio_cash_availability_observations"

    currency = Column(String(3), nullable=False)
    settled_amount = Column(ExactNumeric(), nullable=True)
    encumbered_amount = Column(ExactNumeric(), nullable=True)
    available_amount = Column(ExactNumeric(), nullable=True)

    @staticmethod
    def family_constraints():
        return (
            CheckConstraint("currency ~ '^[A-Z]{3}$'"),
            *(
                finite_numeric_check_constraint(f"ck_cash_observation_{name}_finite", name)
                for name in ("settled_amount", "encumbered_amount", "available_amount")
            ),
        )


class FundingInvestmentObservationRow(ObservationColumns, Base):
    __tablename__ = "portfolio_funding_investment_observations"

    funded = Column(Boolean, nullable=True)
    invested = Column(Boolean, nullable=True)

    @staticmethod
    def family_constraints():
        return ()


class ObservationHeadColumns:
    tenant_id = Column(String(128), primary_key=True)
    portfolio_id = Column(String, primary_key=True)
    producer_id = Column(String(128), primary_key=True)
    source_record_id = Column(String(128), primary_key=True)
    observation_id = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)

    @declared_attr
    def __table_args__(cls):
        return (
            ForeignKeyConstraint(
                [*SOURCE_IDENTITY_COLUMNS, "observation_id", "content_hash"],
                [
                    f"{cls.observation_table}.{name}"
                    for name in (*SOURCE_IDENTITY_COLUMNS, "observation_id", "content_hash")
                ],
            ),
        )


class CashAvailabilityObservationHead(ObservationHeadColumns, Base):
    __tablename__ = "portfolio_cash_availability_observation_heads"
    observation_table = CashAvailabilityObservationRow.__tablename__


class FundingInvestmentObservationHead(ObservationHeadColumns, Base):
    __tablename__ = "portfolio_funding_investment_observation_heads"
    observation_table = FundingInvestmentObservationRow.__tablename__


def observation_from_row(row) -> PortfolioSourceObservation:
    """Reconstruct and verify shared immutable facts, not a cross-service adapter."""
    envelope = ObservationEnvelope(
        **{
            name: getattr(row, name)
            for name in ObservationEnvelope.__dataclass_fields__
            if name != "coverage"
        },
        coverage=ObservationCoverage(row.coverage),
    )
    fact: PortfolioSourceObservation
    if isinstance(row, CashAvailabilityObservationRow):
        fact = CashAvailabilityObservation(
            envelope, row.currency, row.settled_amount, row.encumbered_amount, row.available_amount
        )
    elif isinstance(row, FundingInvestmentObservationRow):
        fact = FundingInvestmentObservation(envelope, row.funded, row.invested)
    else:
        raise TypeError("typed portfolio source observation row required")
    if fact.content_hash != row.content_hash or row.observation_id != row.content_hash:
        raise ObservationConflict("SOURCE_OBSERVATION_HASH_MISMATCH")
    return fact
