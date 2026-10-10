"""Immutable bounded history children of the canonical reference-data facility."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from .db_base import Base


class ClassificationTaxonomyColumns:
    """Effective label dictionary; separate from historical security assignments."""

    id = Column(Integer, primary_key=True, autoincrement=True)
    classification_set_id = Column(String, nullable=False, index=True)
    taxonomy_scope = Column(String, nullable=False, index=True)
    dimension_name = Column(String, nullable=False, index=True)
    dimension_value = Column(String, nullable=False, index=True)
    dimension_description = Column(String, nullable=True)
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    source_vendor = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    quality_status = Column(String, nullable=False, server_default="accepted", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InstrumentClassificationCutRecord(Base):
    __tablename__ = "instrument_classification_cuts"
    cut_id = Column(String(71), primary_key=True)
    content_hash = Column(String(71), nullable=False)
    producer_id = Column(String(128), nullable=False)
    classification_set_id = Column(String(128), nullable=False)
    source_record_id = Column(String(128), nullable=False)
    source_version = Column(Integer, nullable=False)
    predecessor_cut_id = Column(String(71), nullable=True)
    payload = Column(JSONB, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "producer_id", "classification_set_id", "source_record_id", "source_version"
        ),
        UniqueConstraint("producer_id", "classification_set_id", "source_record_id", "cut_id"),
        UniqueConstraint("predecessor_cut_id"),
        ForeignKeyConstraint(
            ["producer_id", "classification_set_id", "source_record_id", "predecessor_cut_id"],
            [
                f"instrument_classification_cuts.{name}"
                for name in ("producer_id", "classification_set_id", "source_record_id", "cut_id")
            ],
        ),
        CheckConstraint(
            "source_version > 0 AND ((source_version = 1) = (predecessor_cut_id IS NULL))"
        ),
        CheckConstraint(
            "cut_id ~ '^sha256:[0-9a-f]{64}$' AND content_hash ~ '^sha256:[0-9a-f]{64}$'"
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object' AND isfinite(received_at)"),
    )
