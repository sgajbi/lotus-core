"""Append-only flow facts and manifests; reuse existing source receipt/head columns."""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)

from .db_base import Base
from .domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowEventPin,
    FlowSourceCut,
)
from .domain.portfolio_source_observations import ObservationCoverage, ObservationEnvelope
from .financial_numeric import ExactNumeric, finite_numeric_check_constraint
from .portfolio_source_observation_models import ObservationColumns, ObservationHeadColumns


class FlowEventObservationRow(ObservationColumns, Base):
    __tablename__ = "portfolio_flow_event_observations"
    business_date = Column(Date, nullable=False)
    currency = Column(String(3), nullable=False)
    amount = Column(ExactNumeric(), nullable=False)
    classification = Column(String(32), nullable=False)
    posting_state = Column(String(16), nullable=False)
    reversal_state = Column(String(16), nullable=False)
    reverses_event_id = Column(String(128), nullable=True)
    reversal_target = Column(JSON(none_as_null=True), nullable=True)
    economic_event_id = Column(String(128), nullable=True)
    transaction_id = Column(String(128), nullable=True)

    @staticmethod
    def family_constraints():
        return (
            Index(
                "ix_flow_source_window_membership",
                "tenant_id",
                "portfolio_id",
                "producer_id",
                "currency",
                "definition_version",
                "business_date",
                "source_record_id",
            ),
            Index(
                "uq_flow_event_successor",
                "predecessor_id",
                unique=True,
                postgresql_where=text("predecessor_id IS NOT NULL"),
            ),
            CheckConstraint("currency ~ '^[A-Z]{3}$'"),
            finite_numeric_check_constraint("ck_flow_observation_amount_finite", "amount"),
            CheckConstraint("posting_state IN ('POSTED','CANCELLED','UNKNOWN')"),
            CheckConstraint("reversal_state IN ('NONE','REVERSES','UNKNOWN')"),
            CheckConstraint(
                "classification IN ('EXTERNAL_CASH','INTERNAL_TRANSFER','REVERSAL','IN_KIND')"
            ),
            CheckConstraint("(reversal_state = 'REVERSES') = (reverses_event_id IS NOT NULL)"),
            CheckConstraint("(reversal_state = 'REVERSES') = (reversal_target IS NOT NULL)"),
            CheckConstraint(
                "reversal_target IS NULL OR (jsonb_typeof(reversal_target::jsonb)='object' "
                "AND jsonb_typeof(reversal_target::jsonb->'source_record_id')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'observation_id')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'content_hash')='string' "
                "AND jsonb_typeof(reversal_target::jsonb->'flow_source_record_revision')='number' "
                "AND reversal_target::jsonb ?& "
                "ARRAY['source_record_id','observation_id','content_hash',"
                "'flow_source_record_revision'] "
                "AND reversal_target::jsonb - 'source_record_id' - 'observation_id' - "
                "'content_hash' - 'flow_source_record_revision' = '{}'::jsonb "
                "AND reversal_target::jsonb->>'source_record_id' = reverses_event_id "
                "AND reversal_target::jsonb->>'observation_id' ~ '^[0-9a-f]{64}$' "
                "AND reversal_target::jsonb->>'content_hash' = "
                "reversal_target::jsonb->>'observation_id' "
                "AND reversal_target::jsonb->>'flow_source_record_revision' ~ '^[1-9][0-9]*$')"
            ),
            CheckConstraint("(classification = 'REVERSAL') = (reversal_state = 'REVERSES')"),
            CheckConstraint("reverses_event_id IS NULL OR reverses_event_id <> source_record_id"),
            CheckConstraint(
                "business_date >= effective_from AND (effective_to IS NULL OR business_date "
                "< effective_to)"
            ),
            CheckConstraint(
                "isfinite(received_at) AND isfinite(observed_at) AND isfinite(generated_at)"
            ),
        )


class FlowEventObservationHead(ObservationHeadColumns, Base):
    __tablename__ = "portfolio_flow_event_observation_heads"
    observation_table = FlowEventObservationRow.__tablename__


class FlowSourceCutRow(Base):
    __tablename__ = "portfolio_flow_source_cuts"
    manifest_hash = Column(String(64), primary_key=True)
    tenant_id = Column(String(128), nullable=False)
    portfolio_id = Column(String, nullable=False)
    source_system = Column(String(128), nullable=False)
    source_cut_id = Column(String(128), nullable=False)
    cut_revision = Column(BigInteger, nullable=False)
    definition_version = Column(String(128), nullable=False)
    currency = Column(String(3), nullable=False)
    coverage_from = Column(Date, nullable=False)
    coverage_to = Column(Date, nullable=False)
    coverage = Column(String(16), nullable=False)
    event_pins = Column(JSON, nullable=False)
    dependency_pins = Column(JSON, nullable=False)
    predecessor_cut_hash = Column(String(64), nullable=True)
    expected_head_hash = Column(String(64), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    receipt_job_id = Column(String, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "portfolio_id", "source_system", "source_cut_id", "cut_revision"
        ),
        UniqueConstraint(
            "tenant_id", "portfolio_id", "source_system", "source_cut_id", "manifest_hash"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id", "source_system", "source_cut_id", "predecessor_cut_hash"],
            [
                "portfolio_flow_source_cuts." + c
                for c in (
                    "tenant_id",
                    "portfolio_id",
                    "source_system",
                    "source_cut_id",
                    "manifest_hash",
                )
            ],
        ),
        CheckConstraint("cut_revision > 0 AND coverage_to >= coverage_from"),
        CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$' AND currency ~ '^[A-Z]{3}$'"),
        CheckConstraint(
            "coverage IN ('complete','partial','missing') AND "
            "jsonb_typeof(event_pins::jsonb)='array'"
        ),
        CheckConstraint("isfinite(received_at)"),
        CheckConstraint("jsonb_array_length(event_pins::jsonb) <= 1000"),
        CheckConstraint(
            "jsonb_typeof(dependency_pins::jsonb)='array' AND "
            "jsonb_array_length(event_pins::jsonb) + "
            "jsonb_array_length(dependency_pins::jsonb) <= 1000"
        ),
        CheckConstraint(
            "(cut_revision=1 AND predecessor_cut_hash IS NULL AND expected_head_hash IS "
            "NULL) OR (cut_revision>1 AND predecessor_cut_hash=expected_head_hash AND "
            "predecessor_cut_hash IS NOT NULL)"
        ),
        Index(
            "uq_flow_cut_successor",
            "predecessor_cut_hash",
            unique=True,
            postgresql_where=text("predecessor_cut_hash IS NOT NULL"),
        ),
    )


def _pin_from_json(value) -> FlowEventPin:
    if type(value) is not dict or set(value) != {
        "source_record_id",
        "observation_id",
        "content_hash",
        "flow_source_record_revision",
    }:
        raise ValueError("retained immutable flow pin is malformed")
    return FlowEventPin(**value)


def flow_from_row(row: FlowEventObservationRow) -> FlowEventObservation:
    envelope = ObservationEnvelope(
        **{
            k: ObservationCoverage(row.coverage) if k == "coverage" else getattr(row, k)
            for k in ObservationEnvelope.__dataclass_fields__
        }
    )
    fact = FlowEventObservation(
        envelope,
        business_date=row.business_date,
        currency=row.currency,
        amount=row.amount,
        classification=row.classification,
        posting_state=row.posting_state,
        reversal_state=row.reversal_state,
        reverses_source_record_id=row.reverses_event_id,
        reversal_target=_pin_from_json(row.reversal_target)
        if row.reversal_target is not None
        else None,
        economic_event_id=row.economic_event_id,
        transaction_id=row.transaction_id,
    )
    if fact.content_hash != row.content_hash or row.observation_id != row.content_hash:
        raise ValueError("retained flow content mismatch")
    if not isinstance(row.received_at, datetime) or row.received_at.utcoffset() is None:
        raise ValueError("retained native receipt unavailable")
    return fact


def cut_from_row(row: FlowSourceCutRow) -> FlowSourceCut:
    cut = FlowSourceCut(
        tenant_id=row.tenant_id,
        portfolio_id=row.portfolio_id,
        source_system=row.source_system,
        source_cut_id=row.source_cut_id,
        cut_revision=row.cut_revision,
        definition_version=row.definition_version,
        currency=row.currency,
        coverage_from=row.coverage_from,
        coverage_to=row.coverage_to,
        coverage=ObservationCoverage(row.coverage),
        event_pins=tuple(_pin_from_json(p) for p in row.event_pins),
        dependency_pins=tuple(_pin_from_json(p) for p in row.dependency_pins),
        predecessor_cut_hash=row.predecessor_cut_hash,
        expected_head_hash=row.expected_head_hash,
    )
    if cut.content_hash != row.manifest_hash:
        raise ValueError("retained manifest mismatch")
    if not isinstance(row.received_at, datetime) or row.received_at.utcoffset() is None:
        raise ValueError("retained cut receipt unavailable")
    return cut


def cut_values(cut: FlowSourceCut) -> dict:
    values = asdict(cut)
    values["coverage"] = cut.coverage.value
    values["event_pins"] = [asdict(p) for p in cut.event_pins]
    values["dependency_pins"] = [asdict(p) for p in cut.dependency_pins]
    return values
