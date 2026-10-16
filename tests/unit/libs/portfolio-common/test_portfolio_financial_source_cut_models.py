"""Real SQLAlchemy metadata proves tenant custody/index/receipt and fencing constraints."""

import hashlib
from datetime import UTC, datetime

import pytest
from portfolio_common import database_models
from portfolio_common.portfolio_financial_source_cut_models import (
    IMMUTABLE_SOURCE_TABLES,
    SCOPE,
    FinancialSourceCaptureLinkRow,
    FinancialSourceCaptureSegmentRow,
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
    ingress_capture_projection,
)
from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("chunk", [False, True])
def test_ingress_capture_preserves_original_bytes_and_first_acquisition_chronology(chunk):
    model = FinancialSourceChunkRow if chunk else FinancialSourceCutRow
    raw = b'{"source_system":"producer"}'
    row = model(
        tenant_id="tenant",
        product_name="PortfolioHistoricalRegistry",
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        raw_bytes=raw,
        raw_hash=hashlib.sha256(raw).hexdigest(),
        received_at=datetime(2026, 10, 16, tzinfo=UTC),
        receipt_job_id="first-receipt",
        **({"chunk_index": 0, "typed_hash": "a" * 64} if chunk else {"content_hash": "a" * 64}),
    )
    projected = ingress_capture_projection(row, chunk=chunk)
    assert (
        projected["serializer_id"]
        == "portfolio-historical-registry-" + ("chunk" if chunk else "cut") + ":ingress-json:v1"
    )
    assert projected["source_page_index"] == (1 if chunk else 0)
    assert projected["source_context"]["captured_at"] is row.received_at
    assert projected["source_context"]["snapshot_epoch"] is None
    assert projected["source_context"]["receipt_job_id"] == "first-receipt"
    assert projected["typed_content_hash"] == "a" * 64
    assert projected["original_supplier_digest"] is None
    row.raw_bytes += b" "
    with pytest.raises(ValueError, match="ingress bytes"):
        ingress_capture_projection(row, chunk=chunk)
    row.raw_bytes = raw
    row.received_at = row.received_at.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timestamp"):
        ingress_capture_projection(row, chunk=chunk)


def foreign_keys(model):
    return {
        tuple(e.parent.name for e in c.elements): tuple(e.target_fullname for e in c.elements)
        for c in model.__table__.constraints
        if isinstance(c, ForeignKeyConstraint)
    }


def test_all_registered_tables_compile_with_actual_native_receipt_and_portfolio_metadata():
    metadata = database_models.IngestionJob.metadata
    for name in (
        *IMMUTABLE_SOURCE_TABLES,
        "portfolio_financial_source_cut_heads",
        "portfolio_financial_source_cut_work",
    ):
        table = metadata.tables[name]
        ddl = str(CreateTable(table).compile(dialect=dialect()))
        assert name in ddl
        for foreign in table.foreign_keys:
            assert foreign.column.table.metadata is metadata


def test_member_mapping_and_input_custody_require_same_tenant_portfolio_and_exact_chunk():
    assert foreign_keys(HistoricalRegistryMemberRow)[("tenant_id", "core_portfolio_id")] == (
        "portfolios.tenant_id",
        "portfolios.portfolio_id",
    )
    assert foreign_keys(FinancialSourceInputRow)[("tenant_id", "portfolio_id")] == (
        "portfolios.tenant_id",
        "portfolios.portfolio_id",
    )
    for model in (HistoricalRegistryMemberRow, FinancialSourceInputRow):
        assert (*SCOPE, "chunk_index") in foreign_keys(model)
    assert (*SCOPE, "portfolio_id") in foreign_keys(FinancialSourceCaptureLinkRow)
    assert ("tenant_id", "capture_id") in foreign_keys(FinancialSourceCaptureSegmentRow)


@pytest.mark.parametrize(
    ("model", "columns"),
    [
        (HistoricalRegistryMemberRow, ("provider_namespace", "source_member_id")),
        (FinancialSourceInputRow, ("portfolio_id",)),
        (FinancialSourceCaptureLinkRow, ("portfolio_id",)),
    ],
)
def test_ordered_identifiers_use_byte_order_independently_of_database_locale(model, columns):
    ddl = str(CreateTable(model.__table__).compile(dialect=dialect()))
    for name in columns:
        assert model.__table__.c[name].type.collation == "C"
        assert f"{name} VARCHAR" in ddl
    assert ddl.count('COLLATE "C"') == len(columns)


def test_bigint_counts_are_not_population_caps_and_raw_page_budget_is_separate():
    for name in ("row_count", "chunk_count"):
        assert isinstance(FinancialSourceCutRow.__table__.c[name].type, BigInteger)
    constraints = " ".join(
        str(c.sqltext)
        for c in FinancialSourceChunkRow.__table__.constraints
        if isinstance(c, CheckConstraint)
    )
    assert "row_count BETWEEN 0 AND 500" in constraints
    assert "octet_length(raw_bytes) BETWEEN 1 AND 1048576" in constraints
    seal = str(CreateTable(FinancialSourceCutRow.__table__).compile(dialect=dialect()))
    assert "row_count <=" not in seal


def test_worker_work_is_not_append_only_capture_and_requires_native_job_scope():
    assert FinancialSourceCutWorkRow.__tablename__ not in IMMUTABLE_SOURCE_TABLES
    assert ("tenant_id", "receipt_job_id") in foreign_keys(FinancialSourceCutWorkRow)
    assert (*SCOPE, "content_hash") in foreign_keys(FinancialSourceCutWorkRow)
    assert any(
        index.name == "ix_financial_source_work_claim"
        for index in FinancialSourceCutWorkRow.__table__.indexes
    )
