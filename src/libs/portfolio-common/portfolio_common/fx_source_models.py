"""Append-only authority children of Core FX, separate from global legacy fx_rates."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .db_base import Base
from .financial_numeric import ExactNumeric, finite_numeric_check_constraint


def _source_text_checks(prefix: str, columns: tuple[str, ...]) -> tuple[CheckConstraint, ...]:
    return tuple(
        CheckConstraint(
            f"{column} <> '' AND {column} = btrim({column}) AND {column} !~ '[[:cntrl:]]'",
            name=f"ck_{prefix}_{column}",
        )
        for column in columns
    )


class FxRateSourceCut(Base):
    __tablename__ = "fx_rate_source_cuts"

    cut_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(128), nullable=False)
    provider_id = Column(String(128), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_cut_reference = Column(String(128), nullable=False)
    source_cut_revision = Column(String(128), nullable=False)
    source_observed_cutoff = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    member_count = Column(Integer, nullable=False)
    members = Column(JSONB, nullable=False)
    membership_hash = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    admission_receipt = Column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("cut_id", "tenant_id", "provider_id", "source_id", name="uq_fx_cut_scope"),
        UniqueConstraint(
            "tenant_id",
            "provider_id",
            "source_id",
            "source_cut_reference",
            "source_cut_revision",
            name="uq_fx_cut_source_version",
        ),
        CheckConstraint("member_count BETWEEN 1 AND 512", name="ck_fx_cut_member_count"),
        CheckConstraint(
            "jsonb_typeof(members) = 'array' AND jsonb_array_length(members) = member_count",
            name="ck_fx_cut_exact_members",
        ),
        CheckConstraint(
            "isfinite(source_observed_cutoff) AND isfinite(accepted_at) "
            "AND source_observed_cutoff <= accepted_at",
            name="ck_fx_cut_time",
        ),
        *(
            CheckConstraint(f"{column} ~ '^[0-9a-f]{{64}}$'", name=f"ck_fx_cut_{column}")
            for column in ("cut_id", "membership_hash", "content_hash")
        ),
        *_source_text_checks(
            "fx_cut",
            (
                "tenant_id",
                "provider_id",
                "source_id",
                "source_cut_reference",
                "source_cut_revision",
            ),
        ),
        Index("ix_fx_cut_historical_scope", "tenant_id", "provider_id", "source_id", "accepted_at"),
    )


class FxRateSourceRevision(Base):
    __tablename__ = "fx_rate_source_revisions"

    revision_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(128), nullable=False)
    provider_id = Column(String(128), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_record_id = Column(String(128), nullable=False)
    source_revision = Column(String(128), nullable=False)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate = Column(ExactNumeric(18, 10), nullable=False)
    source_observed_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    fixing_kind = Column(String(128), nullable=False)
    calendar_version = Column(String(128), nullable=False)
    predecessor_revision_id = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=False)
    admitted_cut_id = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider_id",
            "source_id",
            "source_record_id",
            "source_revision",
            name="uq_fx_revision_source_version",
        ),
        UniqueConstraint(
            "revision_id",
            "tenant_id",
            "provider_id",
            "source_id",
            "source_record_id",
            "from_currency",
            "to_currency",
            "rate_date",
            name="uq_fx_revision_chain_scope",
        ),
        ForeignKeyConstraint(
            ["admitted_cut_id", "tenant_id", "provider_id", "source_id"],
            [
                "fx_rate_source_cuts.cut_id",
                "fx_rate_source_cuts.tenant_id",
                "fx_rate_source_cuts.provider_id",
                "fx_rate_source_cuts.source_id",
            ],
            name="fk_fx_revision_admission_scope",
        ),
        ForeignKeyConstraint(
            [
                "predecessor_revision_id",
                "tenant_id",
                "provider_id",
                "source_id",
                "source_record_id",
                "from_currency",
                "to_currency",
                "rate_date",
            ],
            [
                f"fx_rate_source_revisions.{column}"
                for column in (
                    "revision_id",
                    "tenant_id",
                    "provider_id",
                    "source_id",
                    "source_record_id",
                    "from_currency",
                    "to_currency",
                    "rate_date",
                )
            ],
            name="fk_fx_revision_same_chain",
        ),
        UniqueConstraint("predecessor_revision_id", name="uq_fx_revision_single_child"),
        Index(
            "uq_fx_revision_single_root",
            "tenant_id",
            "provider_id",
            "source_id",
            "source_record_id",
            unique=True,
            postgresql_where=text("predecessor_revision_id IS NULL"),
        ),
        CheckConstraint(
            "predecessor_revision_id IS NULL OR predecessor_revision_id <> revision_id",
            name="ck_fx_revision_not_self",
        ),
        CheckConstraint(
            "from_currency ~ '^[A-Z]{3}$' AND to_currency ~ '^[A-Z]{3}$' "
            "AND from_currency <> to_currency",
            name="ck_fx_revision_pair",
        ),
        CheckConstraint("rate > 0", name="ck_fx_revision_positive_rate"),
        finite_numeric_check_constraint("ck_fx_revision_finite_rate", "rate"),
        CheckConstraint(
            "isfinite(source_observed_at) AND isfinite(accepted_at) "
            "AND source_observed_at <= accepted_at",
            name="ck_fx_revision_time",
        ),
        *(
            CheckConstraint(f"{column} ~ '^[0-9a-f]{{64}}$'", name=f"ck_fx_revision_{column}")
            for column in ("revision_id", "content_hash")
        ),
        *_source_text_checks(
            "fx_revision",
            (
                "tenant_id",
                "provider_id",
                "source_id",
                "source_record_id",
                "source_revision",
                "fixing_kind",
                "calendar_version",
            ),
        ),
    )
