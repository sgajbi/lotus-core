"""Neutral immutable declarations/captures and mutable fenced work, not economic balances."""

import hashlib
import json
from typing import TypeVar, cast

from pydantic import TypeAdapter
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)

from .analytics_export_source_identity import export_source_selection_digest
from .db_base import Base
from .domain.calculation_lineage import canonical_content_hash
from .domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowSourceCut,
    require_flow_cut_events,
)
from .domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
)

SCOPE = (
    "tenant_id",
    "product_name",
    "source_system",
    "registry_scope_id",
    "source_cut_id",
    "revision",
)
PRODUCT_SQL = "product_name IN ('PortfolioHistoricalRegistry','PortfolioFinancialSourceCut')"

INGRESS_CAPTURE_SERIALIZERS = {
    ("PortfolioHistoricalRegistry", False): "portfolio-historical-registry-cut:ingress-json:v1",
    ("PortfolioHistoricalRegistry", True): "portfolio-historical-registry-chunk:ingress-json:v1",
    ("PortfolioFinancialSourceCut", False): "portfolio-financial-source-cut:ingress-json:v1",
    ("PortfolioFinancialSourceCut", True): "portfolio-financial-source-cut-chunk:ingress-json:v1",
}

NATIVE_CAPTURE_SERIALIZERS = {
    "CASH": "portfolio-cash-availability:domain-json:v1",
    "READINESS": "portfolio-funding-investment:domain-json:v1",
    "FLOWS": "portfolio-flow-source-cut:domain-json:v1",
    "PRIOR_ASSETS": "portfolio-timeseries-export:retained-json:v1",
    "MONTH_END_ASSETS": "portfolio-timeseries-export:retained-json:v1",
}


CapturedDomain = TypeVar("CapturedDomain")


def _closed_captured_domain(model: type[CapturedDomain], value) -> CapturedDomain:
    adapter = TypeAdapter(model)
    domain = adapter.validate_json(json.dumps(value, allow_nan=False), strict=True)
    if adapter.dump_python(domain, mode="json") != value:
        raise ValueError("capture requires the complete canonical JSON-mode native domain DTO")
    return cast(CapturedDomain, domain)


def native_capture_typed_root(serializer_id: str, payload: dict) -> str:
    """Independent native-domain/export commitment recipe; matching hashes confer no authority."""
    expected_product = (
        "PortfolioFinancialSourceObservations"
        if serializer_id
        in {NATIVE_CAPTURE_SERIALIZERS["CASH"], NATIVE_CAPTURE_SERIALIZERS["READINESS"]}
        else "PortfolioFinancialFlowObservations"
        if serializer_id == NATIVE_CAPTURE_SERIALIZERS["FLOWS"]
        else "PortfolioTimeseriesInput"
    )
    if payload.get("product_name") != expected_product or payload.get("product_version") != "v1":
        raise ValueError("captured native product/version mismatch")
    if serializer_id == NATIVE_CAPTURE_SERIALIZERS["CASH"]:
        root = _closed_captured_domain(CashAvailabilityObservation, payload["fact"]).content_hash
        if payload["content_hash"] != root or payload["observation_id"] != root:
            raise ValueError("captured cash typed pin mismatch")
        return cast(str, root)
    if serializer_id == NATIVE_CAPTURE_SERIALIZERS["READINESS"]:
        root = _closed_captured_domain(FundingInvestmentObservation, payload["fact"]).content_hash
        if payload["content_hash"] != root or payload["observation_id"] != root:
            raise ValueError("captured readiness typed pin mismatch")
        return cast(str, root)
    if serializer_id == NATIVE_CAPTURE_SERIALIZERS["FLOWS"]:
        cut = _closed_captured_domain(FlowSourceCut, payload["cut"])
        events = tuple(
            _closed_captured_domain(FlowEventObservation, item["fact"])
            for item in payload["events"]
        )
        dependencies = tuple(
            _closed_captured_domain(FlowEventObservation, item["fact"])
            for item in payload["dependencies"]
        )
        if not require_flow_cut_events(cut, events, dependencies):
            raise ValueError("captured native flow coverage incomplete")
        return cast(str, cut.content_hash)
    if serializer_id == NATIVE_CAPTURE_SERIALIZERS["PRIOR_ASSETS"]:
        result = payload["result"]
        digest = export_source_selection_digest(result["data"], result["source_evidence"])
        if result["source_evidence"].get("selection_digest") != digest:
            raise ValueError("captured export selection digest mismatch")
        return digest[len("sha256:") :]
    raise ValueError("unsupported native source-capture serializer")


def ingress_capture_projection(row, *, chunk: bool) -> dict:
    """Pinned ingress artifact tags; raw bytes are original JSON, without a DTO wrapper."""
    if type(chunk) is not bool or type(row) is not (
        FinancialSourceChunkRow if chunk else FinancialSourceCutRow
    ):
        raise ValueError("actual immutable ingress row and explicit kind required")
    if type(row.raw_bytes) is not bytes or not 0 < len(row.raw_bytes) <= 1048576:
        raise ValueError("bounded retained ingress bytes required")
    if (
        row.received_at.utcoffset() is None
        or hashlib.sha256(row.raw_bytes).hexdigest() != row.raw_hash
    ):
        raise ValueError("retained ingress bytes or first receipt timestamp invalid")
    serializer = INGRESS_CAPTURE_SERIALIZERS[(row.product_name, chunk)]
    identity = {key: getattr(row, key) for key in SCOPE}
    page_index = row.chunk_index + 1 if chunk else 0
    return dict(
        capture_id=canonical_content_hash(
            {
                "contract": "NeutralIngressSourceCapture:v1",
                **identity,
                "source_page_index": page_index,
                "raw_hash": row.raw_hash,
            }
        ),
        role=None,
        source_page_index=page_index,
        source_product=row.product_name,
        product_version="v1",
        selector_hash=None,
        typed_content_hash=row.typed_hash if chunk else row.content_hash,
        raw_hash=row.raw_hash,
        byte_count=len(row.raw_bytes),
        segment_count=(len(row.raw_bytes) + 524287) // 524288,
        serializer_id=serializer,
        schema_version="v1",
        mime_type="application/json",
        original_supplier_digest=None,
        original_supplier_reference=None,
        source_context=dict(
            capture_origin="INGRESS_JSON",
            captured_at=row.received_at,
            snapshot_epoch=None,
            request_scope=None,
            receipt_job_id=row.receipt_job_id,
            source_revision=str(row.revision),
            selector_json=None,
            export_job_id=None,
            refresh_of_job_id=None,
            returned_count=None,
            total_count=None,
            next_page_token=None,
        ),
    )


class CutScopeColumns:
    tenant_id = Column(String(128), primary_key=True)
    product_name = Column(String(64), primary_key=True)
    source_system = Column(String(128), primary_key=True)
    registry_scope_id = Column(String(128), primary_key=True)
    source_cut_id = Column(String(128), primary_key=True)
    revision = Column(BigInteger, primary_key=True)


class FinancialSourceCutRow(CutScopeColumns, Base):
    __tablename__ = "portfolio_financial_source_cut_manifests"
    content_hash = Column(String(64), nullable=False)
    raw_hash = Column(String(64), nullable=False)
    raw_bytes = Column(LargeBinary, nullable=False)
    declaration = Column(JSON, nullable=False)
    row_count = Column(BigInteger, nullable=False)
    chunk_count = Column(BigInteger, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    receipt_job_id = Column(String, nullable=False)
    __table_args__ = (
        UniqueConstraint(*SCOPE, "content_hash"),
        ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        CheckConstraint(PRODUCT_SQL),
        CheckConstraint("revision > 0 AND row_count >= 0 AND chunk_count >= 0"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$' AND isfinite(received_at)"),
        CheckConstraint("jsonb_typeof(declaration::jsonb) = 'object'"),
        CheckConstraint(
            "raw_hash ~ '^[0-9a-f]{64}$' AND octet_length(raw_bytes) BETWEEN 1 AND 1048576"
        ),
        Index("ix_financial_manifest_exact_root", "tenant_id", "product_name", "content_hash"),
    )


class FinancialSourceChunkRow(CutScopeColumns, Base):
    __tablename__ = "portfolio_financial_source_cut_chunks"
    chunk_index = Column(BigInteger, primary_key=True)
    typed_hash = Column(String(64), nullable=False)
    raw_hash = Column(String(64), nullable=False)
    raw_bytes = Column(LargeBinary, nullable=False)
    row_count = Column(BigInteger, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    receipt_job_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        CheckConstraint(PRODUCT_SQL),
        CheckConstraint("revision > 0 AND chunk_index >= 0 AND row_count BETWEEN 0 AND 500"),
        CheckConstraint("octet_length(raw_bytes) BETWEEN 1 AND 1048576"),
        CheckConstraint("typed_hash ~ '^[0-9a-f]{64}$' AND raw_hash ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("isfinite(received_at)"),
    )


class HistoricalRegistryMemberRow(CutScopeColumns, Base):
    __tablename__ = "portfolio_historical_registry_members"
    # Match canonical Python identifier ordering independently of database locale.
    provider_namespace = Column(String(128, collation="C"), primary_key=True)
    source_member_id = Column(String(128, collation="C"), primary_key=True)
    chunk_index = Column(BigInteger, nullable=False)
    core_portfolio_id = Column(String, nullable=True)
    member_revision = Column(BigInteger, nullable=False)
    content_hash = Column(String(64), nullable=False)
    declaration = Column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            [*SCOPE, "chunk_index"],
            ["portfolio_financial_source_cut_chunks." + c for c in (*SCOPE, "chunk_index")],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "core_portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        CheckConstraint("product_name = 'PortfolioHistoricalRegistry' AND member_revision > 0"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(declaration::jsonb)='object'"
        ),
        Index(
            "ix_registry_member_core_portfolio",
            "tenant_id",
            "core_portfolio_id",
            "registry_scope_id",
            "revision",
        ),
    )


class FinancialSourceInputRow(CutScopeColumns, Base):
    __tablename__ = "portfolio_financial_source_cut_inputs"
    portfolio_id = Column(String(collation="C"), primary_key=True)
    chunk_index = Column(BigInteger, nullable=False)
    content_hash = Column(String(64), nullable=False)
    declaration = Column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            [*SCOPE, "chunk_index"],
            ["portfolio_financial_source_cut_chunks." + c for c in (*SCOPE, "chunk_index")],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"], ["portfolios.tenant_id", "portfolios.portfolio_id"]
        ),
        CheckConstraint("product_name = 'PortfolioFinancialSourceCut'"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(declaration::jsonb)='object'"
        ),
        Index(
            "ix_financial_cut_portfolio_revision",
            "tenant_id",
            "portfolio_id",
            "source_system",
            "revision",
        ),
    )


class FinancialSourceHeadRow(Base):
    __tablename__ = "portfolio_financial_source_cut_heads"
    tenant_id = Column(String(128), primary_key=True)
    product_name = Column(String(64), primary_key=True)
    source_system = Column(String(128), primary_key=True)
    registry_scope_id = Column(String(128), primary_key=True)
    source_cut_id = Column(String(128), primary_key=True)
    revision = Column(BigInteger, nullable=False)
    content_hash = Column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            [*SCOPE, "content_hash"],
            ["portfolio_financial_source_cut_manifests." + c for c in (*SCOPE, "content_hash")],
        ),
        CheckConstraint(PRODUCT_SQL),
    )


class FinancialSourceCaptureRow(Base):
    __tablename__ = "portfolio_financial_source_captures"
    tenant_id = Column(String(128), primary_key=True)
    capture_id = Column(String(64), primary_key=True)
    source_product = Column(String(64), nullable=False)
    product_version = Column(String(32), nullable=False)
    selector_hash = Column(String(64), nullable=False)
    typed_content_hash = Column(String(64), nullable=False)
    raw_hash = Column(String(64), nullable=False)
    byte_count = Column(BigInteger, nullable=False)
    segment_count = Column(BigInteger, nullable=False)
    serializer_id = Column(String(128), nullable=False)
    mime_type = Column(String(128), nullable=False)
    source_context = Column(JSON, nullable=False)
    original_supplier_digest = Column(String(64), nullable=True)
    original_supplier_reference = Column(String(128), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "capture_id ~ '^[0-9a-f]{64}$' AND selector_hash ~ '^[0-9a-f]{64}$' "
            "AND typed_content_hash ~ '^[0-9a-f]{64}$' AND raw_hash ~ '^[0-9a-f]{64}$'"
        ),
        CheckConstraint("byte_count >= 0 AND segment_count > 0"),
        CheckConstraint("jsonb_typeof(source_context::jsonb)='object'"),
        CheckConstraint(
            "(original_supplier_digest IS NULL) = (original_supplier_reference IS NULL)"
        ),
        CheckConstraint(
            "original_supplier_digest IS NULL OR original_supplier_digest ~ '^[0-9a-f]{64}$'"
        ),
        Index(
            "ix_financial_capture_exact_source",
            "tenant_id",
            "source_product",
            "selector_hash",
            "raw_hash",
        ),
    )


class FinancialSourceCaptureSegmentRow(Base):
    __tablename__ = "portfolio_financial_source_capture_segments"
    tenant_id = Column(String(128), primary_key=True)
    capture_id = Column(String(64), primary_key=True)
    segment_index = Column(BigInteger, primary_key=True)
    raw_bytes = Column(LargeBinary, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "capture_id"],
            [
                "portfolio_financial_source_captures.tenant_id",
                "portfolio_financial_source_captures.capture_id",
            ],
        ),
        CheckConstraint("segment_index >= 0 AND octet_length(raw_bytes) <= 524288"),
    )


class FinancialSourceCaptureLinkRow(CutScopeColumns, Base):
    __tablename__ = "portfolio_financial_source_capture_links"
    portfolio_id = Column(String(collation="C"), primary_key=True)
    role = Column(String(32), primary_key=True)
    page_index = Column(BigInteger, primary_key=True)
    capture_id = Column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            [*SCOPE, "portfolio_id"],
            ["portfolio_financial_source_cut_inputs." + c for c in (*SCOPE, "portfolio_id")],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "capture_id"],
            [
                "portfolio_financial_source_captures.tenant_id",
                "portfolio_financial_source_captures.capture_id",
            ],
        ),
        CheckConstraint(
            "page_index >= 0 AND "
            "role IN ('PRIOR_ASSETS','MONTH_END_ASSETS','CASH','READINESS','FLOWS')"
        ),
    )


class FinancialSourceCutWorkRow(Base):
    __tablename__ = "portfolio_financial_source_cut_work"
    work_id = Column(String(36), primary_key=True)
    partition_index = Column(BigInteger, nullable=False, default=0, server_default="0")
    tenant_id = Column(String(128), nullable=False)
    product_name = Column(String(64), nullable=False)
    source_system = Column(String(128), nullable=False)
    registry_scope_id = Column(String(128), nullable=False)
    source_cut_id = Column(String(128), nullable=False)
    revision = Column(BigInteger, nullable=False)
    content_hash = Column(String(64), nullable=False)
    receipt_job_id = Column(String, nullable=False)
    status = Column(String(16), nullable=False, server_default="PENDING")
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    checkpoint = Column(JSON, nullable=False)
    available_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    attempts = Column(BigInteger, nullable=False, server_default="0")
    last_error_code = Column(String(64), nullable=True)
    __table_args__ = (
        UniqueConstraint(*SCOPE, "partition_index"),
        ForeignKeyConstraint(
            [*SCOPE, "content_hash"],
            ["portfolio_financial_source_cut_manifests." + c for c in (*SCOPE, "content_hash")],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "receipt_job_id"], ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"]
        ),
        CheckConstraint("status IN ('PENDING','CLAIMED','COMPLETED','FAILED') AND attempts >= 0"),
        CheckConstraint("partition_index >= 0"),
        CheckConstraint(
            "(status = 'CLAIMED' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'CLAIMED' AND lease_token IS NULL AND lease_expires_at IS NULL)"
        ),
        CheckConstraint("jsonb_typeof(checkpoint::jsonb)='object' AND isfinite(available_at)"),
        Index("ix_financial_source_work_claim", "status", "available_at", "tenant_id", "work_id"),
    )


IMMUTABLE_SOURCE_TABLES = (
    FinancialSourceCutRow.__tablename__,
    FinancialSourceChunkRow.__tablename__,
    HistoricalRegistryMemberRow.__tablename__,
    FinancialSourceInputRow.__tablename__,
    FinancialSourceCaptureRow.__tablename__,
    FinancialSourceCaptureSegmentRow.__tablename__,
    FinancialSourceCaptureLinkRow.__tablename__,
)
