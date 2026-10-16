"""Adapter query fences and retained ingress roots; no database execution."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceCutRow,
    ingress_capture_projection,
)
from pydantic import TypeAdapter
from sqlalchemy.dialects import postgresql

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_financial_source_cuts as retained,
)
from tests.unit.services.query_control_plane_service.application import (
    test_portfolio_financial_source_cuts as read_tests,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path,bad",
    [
        (("expected_population", "unexpected"), True),
        (("expected_population", "count"), True),
        (("expected_population", "count"), "0"),
        (("revision",), True),
        (("revision",), "1"),
        (("supplied_count",), True),
        (("chunk_count",), "0"),
        (("observed_at",), "2026-10-16T00:00:00"),
        (("generated_at",), 1792108800),
        (("coverage_to",), "2024-12-31"),
        (("declared_coverage",), "QUALIFIED"),
        (("members_root",), "invalid"),
        (("predecessor_hash",), "a" * 64),
        (("expected_population", "count"), float("nan")),
    ],
)
def test_qcp_manifest_refuses_nested_extras_and_coercion(path, bad):
    _, row, _, _ = persisted_registry()
    target = row.declaration
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = bad
    with pytest.raises(ValueError):
        retained.manifest_from_payload(row.declaration, row.tenant_id, row.product_name)


# Producer-owned independent mocked-source vectors, public freeze6214040997.
# Source packet SHA256a6bbdfdfe714b62f005fb0db1d75503dbfa66b27cd67915fcf34f70b4495d258.
# Exact bytes and expected roots are copied unchanged; these are synthetic, not native receipts.
NATIVE_CAPTURE_VECTOR_SOURCE_SHA256 = (
    "a6bbdfdfe714b62f005fb0db1d75503dbfa66b27cd67915fcf34f70b4495d258"
)
NATIVE_CAPTURE_VECTORS = {
    "CASH": {
        "serializer_id": "portfolio-cash-availability:domain-json:v1",
        "schema_version": "v1",
        "typed_root": "0b19b6e4708fc39113ff88985cbd0a4ddeb3944139d05e4d8f6e9d53ed971d48",
        "raw_sha256": "b22121e814cc22c2dacdadd54159d327e08bb4a3cb8c297d5e0f97e7026daa22",
        "bytes_base64": (
            "eyJwYXlsb2FkIjp7ImNvbnRlbnRfaGFzaCI6IjBiMTliNmU0NzA4ZmMzOTExM2ZmODg5ODVjYmQw"
            "YTRkZGViMzk0NDEzOWQwNWU0ZDhmNmU5ZDUzZWQ5NzFkNDgiLCJmYWN0Ijp7ImF2YWlsYWJsZSI6"
            "bnVsbCwiY3VycmVuY3kiOiJVU0QiLCJlbmN1bWJlcmVkIjpudWxsLCJlbnZlbG9wZSI6eyJjb3Zl"
            "cmFnZSI6ImNvbXBsZXRlIiwiY292ZXJhZ2Vfc2NvcGUiOiJkZWNsYXJlZC1zY29wZSIsImRlZmlu"
            "aXRpb25fdmVyc2lvbiI6InYxIiwiZWZmZWN0aXZlX2Zyb20iOiIyMDI1LTAxLTAxIiwiZWZmZWN0"
            "aXZlX3RvIjpudWxsLCJleHBlY3RlZF9oZWFkX2hhc2giOm51bGwsImdlbmVyYXRlZF9hdCI6IjIw"
            "MjYtMTAtMTZUMDA6MDA6MDBaIiwib2JzZXJ2ZWRfYXQiOiIyMDI2LTEwLTE2VDAwOjAwOjAwWiIs"
            "InBvcnRmb2xpb19pZCI6InBvcnRmb2xpbyIsInByZWRlY2Vzc29yX2lkIjpudWxsLCJwcm9kdWNl"
            "cl9pZCI6InByb2R1Y2VyIiwic291cmNlX2N1dF9pZCI6ImN1dCIsInNvdXJjZV9yZWNvcmRfaWQi"
            "OiJyZWNvcmQiLCJzb3VyY2VfcmV2aXNpb24iOjEsInRlbmFudF9pZCI6InRlbmFudCJ9LCJzZXR0"
            "bGVkIjoiMC4wMCJ9LCJvYnNlcnZhdGlvbl9pZCI6IjBiMTliNmU0NzA4ZmMzOTExM2ZmODg5ODVj"
            "YmQwYTRkZGViMzk0NDEzOWQwNWU0ZDhmNmU5ZDUzZWQ5NzFkNDgiLCJwcm9kdWN0X25hbWUiOiJQ"
            "b3J0Zm9saW9GaW5hbmNpYWxTb3VyY2VPYnNlcnZhdGlvbnMiLCJwcm9kdWN0X3ZlcnNpb24iOiJ2"
            "MSIsInJlY2VpcHQiOnsiYWNjZXB0ZWRfY291bnQiOjEsImNvbXBsZXRlZF9hdCI6IjIwMjYtMTAt"
            "MTZUMDA6MDA6MDArMDA6MDAiLCJlbmRwb2ludCI6Ii9pbmdlc3QvcG9ydGZvbGlvLWNhc2gtYXZh"
            "aWxhYmlsaXR5LW9ic2VydmF0aW9ucyIsImVudGl0eV90eXBlIjoicG9ydGZvbGlvX2Nhc2hfYXZh"
            "aWxhYmlsaXR5X29ic2VydmF0aW9uIiwiam9iX2lkIjoicmVjZWlwdCIsInN0YXR1cyI6ImNvbXBs"
            "ZXRlZCIsInRlbmFudF9pZCI6InRlbmFudCJ9LCJyZWNlaXZlZF9hdCI6IjIwMjYtMTAtMTZUMDA6"
            "MDA6MDArMDA6MDAifSwic2VyaWFsaXplciI6InBvcnRmb2xpby1jYXNoLWF2YWlsYWJpbGl0eTpk"
            "b21haW4tanNvbjp2MSJ9"
        ),
    },
    "FLOWS": {
        "serializer_id": "portfolio-flow-source-cut:domain-json:v1",
        "schema_version": "v1",
        "typed_root": "ae7cf233e1dc231ef4a23796c1d1df812b1e3f3ae557473599bd0d3f79b5797a",
        "raw_sha256": "795eb18580f26783feab8a1bad4130b8595c5bbc6f3d2123cec4a4dfe90e552b",
        "bytes_base64": (
            "eyJwYXlsb2FkIjp7ImN1dCI6eyJjb3ZlcmFnZSI6ImNvbXBsZXRlIiwiY292ZXJhZ2VfZnJvbSI6"
            "IjIwMjUtMDEtMDEiLCJjb3ZlcmFnZV90byI6IjIwMjUtMDEtMzEiLCJjdXJyZW5jeSI6IlVTRCIs"
            "ImN1dF9yZXZpc2lvbiI6MSwiZGVmaW5pdGlvbl92ZXJzaW9uIjoidjEiLCJkZXBlbmRlbmN5X3Bp"
            "bnMiOltdLCJldmVudF9waW5zIjpbeyJjb250ZW50X2hhc2giOiIyZDk4YTE4YjdhYWZkMmM4MDI5"
            "ODczZDA1MmRmMDc0ZDRhNzgxZmM3ZjMyYzFiZmI4MTgwNGMwODYyOWQxOWU4IiwiZmxvd19zb3Vy"
            "Y2VfcmVjb3JkX3JldmlzaW9uIjoxLCJvYnNlcnZhdGlvbl9pZCI6IjJkOThhMThiN2FhZmQyYzgw"
            "Mjk4NzNkMDUyZGYwNzRkNGE3ODFmYzdmMzJjMWJmYjgxODA0YzA4NjI5ZDE5ZTgiLCJzb3VyY2Vf"
            "cmVjb3JkX2lkIjoicmVjb3JkIn1dLCJleHBlY3RlZF9oZWFkX2hhc2giOm51bGwsInBvcnRmb2xp"
            "b19pZCI6InBvcnRmb2xpbyIsInByZWRlY2Vzc29yX2N1dF9oYXNoIjpudWxsLCJzb3VyY2VfY3V0"
            "X2lkIjoiZmxvdy1jdXQiLCJzb3VyY2Vfc3lzdGVtIjoicHJvZHVjZXIiLCJ0ZW5hbnRfaWQiOiJ0"
            "ZW5hbnQifSwiZGVwZW5kZW5jaWVzIjpbXSwiZXZlbnRzIjpbeyJmYWN0Ijp7ImFtb3VudCI6Ii0x"
            "MC4wMCIsImJ1c2luZXNzX2RhdGUiOiIyMDI1LTAxLTMxIiwiY2xhc3NpZmljYXRpb24iOiJFWFRF"
            "Uk5BTF9DQVNIIiwiY3VycmVuY3kiOiJVU0QiLCJlY29ub21pY19ldmVudF9pZCI6bnVsbCwiZW52"
            "ZWxvcGUiOnsiY292ZXJhZ2UiOiJjb21wbGV0ZSIsImNvdmVyYWdlX3Njb3BlIjoiZGVjbGFyZWQt"
            "c2NvcGUiLCJkZWZpbml0aW9uX3ZlcnNpb24iOiJ2MSIsImVmZmVjdGl2ZV9mcm9tIjoiMjAyNS0w"
            "MS0wMSIsImVmZmVjdGl2ZV90byI6bnVsbCwiZXhwZWN0ZWRfaGVhZF9oYXNoIjpudWxsLCJnZW5l"
            "cmF0ZWRfYXQiOiIyMDI2LTEwLTE2VDAwOjAwOjAwWiIsIm9ic2VydmVkX2F0IjoiMjAyNi0xMC0x"
            "NlQwMDowMDowMFoiLCJwb3J0Zm9saW9faWQiOiJwb3J0Zm9saW8iLCJwcmVkZWNlc3Nvcl9pZCI6"
            "bnVsbCwicHJvZHVjZXJfaWQiOiJwcm9kdWNlciIsInNvdXJjZV9jdXRfaWQiOiJjdXQiLCJzb3Vy"
            "Y2VfcmVjb3JkX2lkIjoicmVjb3JkIiwic291cmNlX3JldmlzaW9uIjoxLCJ0ZW5hbnRfaWQiOiJ0"
            "ZW5hbnQifSwicG9zdGluZ19zdGF0ZSI6IlBPU1RFRCIsInJldmVyc2FsX3N0YXRlIjoiTk9ORSIs"
            "InJldmVyc2FsX3RhcmdldCI6bnVsbCwicmV2ZXJzZXNfc291cmNlX3JlY29yZF9pZCI6bnVsbCwi"
            "dHJhbnNhY3Rpb25faWQiOm51bGx9LCJyZWNlaXB0Ijp7ImFjY2VwdGVkX2NvdW50IjoxLCJjb21w"
            "bGV0ZWRfYXQiOiIyMDI2LTEwLTE2VDAwOjAwOjAwKzAwOjAwIiwiZW5kcG9pbnQiOiIvaW5nZXN0"
            "L3BvcnRmb2xpby1mbG93LWV2ZW50LW9ic2VydmF0aW9ucyIsImVudGl0eV90eXBlIjoicG9ydGZv"
            "bGlvX2Zsb3dfZXZlbnRfb2JzZXJ2YXRpb24iLCJqb2JfaWQiOiJldmVudC1yZWNlaXB0Iiwic3Rh"
            "dHVzIjoiY29tcGxldGVkIiwidGVuYW50X2lkIjoidGVuYW50In0sInJlY2VpdmVkX2F0IjoiMjAy"
            "Ni0xMC0xNlQwMDowMDowMCswMDowMCJ9XSwicHJvZHVjdF9uYW1lIjoiUG9ydGZvbGlvRmluYW5j"
            "aWFsRmxvd09ic2VydmF0aW9ucyIsInByb2R1Y3RfdmVyc2lvbiI6InYxIiwicmVjZWlwdCI6eyJh"
            "Y2NlcHRlZF9jb3VudCI6MSwiY29tcGxldGVkX2F0IjoiMjAyNi0xMC0xNlQwMDowMDowMCswMDow"
            "MCIsImVuZHBvaW50IjoiL2luZ2VzdC9wb3J0Zm9saW8tZmxvdy1zb3VyY2UtY3V0cyIsImVudGl0"
            "eV90eXBlIjoicG9ydGZvbGlvX2Zsb3dfc291cmNlX2N1dCIsImpvYl9pZCI6ImN1dC1yZWNlaXB0"
            "Iiwic3RhdHVzIjoiY29tcGxldGVkIiwidGVuYW50X2lkIjoidGVuYW50In0sInJlY2VpdmVkX2F0"
            "IjoiMjAyNi0xMC0xNlQwMDowMDowMCswMDowMCJ9LCJzZXJpYWxpemVyIjoicG9ydGZvbGlvLWZs"
            "b3ctc291cmNlLWN1dDpkb21haW4tanNvbjp2MSJ9"
        ),
    },
    "MONTH_END_ASSETS": {
        "serializer_id": "portfolio-timeseries-export:retained-json:v1",
        "schema_version": "v1",
        "typed_root": "19190e048d9a398e271229a5bcd0bc09ab772c49f0938f401c92fbb409d7fb25",
        "raw_sha256": "fb715b6a491cfca4954c819c92e0864da7e8d909cc3526a28061abc6cfcc6a3c",
        "bytes_base64": (
            "eyJwYXlsb2FkIjp7InByb2R1Y3RfbmFtZSI6IlBvcnRmb2xpb1RpbWVzZXJpZXNJbnB1dCIsInBy"
            "b2R1Y3RfdmVyc2lvbiI6InYxIiwicmVjZWlwdCI6eyJjb21wbGV0ZWRfYXQiOiIyMDI2LTEwLTE2"
            "VDAwOjAwOjAwKzAwOjAwIiwiZGF0YXNldF90eXBlIjoicG9ydGZvbGlvX3RpbWVzZXJpZXMiLCJq"
            "b2JfaWQiOiJleHBvcnQiLCJwb3J0Zm9saW9faWQiOiJwb3J0Zm9saW8iLCJyZXN1bHRfcm93X2Nv"
            "dW50IjoxLCJzdGF0dXMiOiJjb21wbGV0ZWQifSwicmVxdWVzdCI6eyJkYXRhc2V0X3R5cGUiOiJw"
            "b3J0Zm9saW9fdGltZXNlcmllcyIsInBvcnRmb2xpb19pZCI6InBvcnRmb2xpbyIsInBvcnRmb2xp"
            "b190aW1lc2VyaWVzX3JlcXVlc3QiOnsiYXNfb2ZfZGF0ZSI6IjIwMjUtMDEtMzEiLCJjb25zdW1l"
            "cl9zeXN0ZW0iOiJsb3R1cy1tYW5hZ2UiLCJwZXJpb2QiOm51bGwsInJlcG9ydGluZ19jdXJyZW5j"
            "eSI6IlVTRCIsIndpbmRvdyI6eyJlbmRfZGF0ZSI6IjIwMjUtMDEtMzEiLCJzdGFydF9kYXRlIjoi"
            "MjAyNS0wMS0zMSJ9fX0sInJlc3VsdCI6eyJkYXRhIjpbeyJlb2RfbWFya2V0X3ZhbHVlIjoiMTAw"
            "LjAwIiwidmFsdWF0aW9uX2RhdGUiOiIyMDI1LTAxLTMxIn1dLCJkYXRhc2V0X3R5cGUiOiJwb3J0"
            "Zm9saW9fdGltZXNlcmllcyIsImpvYl9pZCI6ImV4cG9ydCIsInJlc3VsdF9yb3dfY291bnQiOjEs"
            "InNvdXJjZV9ldmlkZW5jZSI6eyJhdmFpbGFiaWxpdHkiOiJSRVRBSU5FRCIsInBhZ2VzIjpbeyJw"
            "YWdlX251bWJlciI6MSwicmVxdWVzdGVkX3Njb3BlIjp7ImFzX29mX2RhdGUiOiIyMDI1LTAxLTMx"
            "IiwiY29uc3VtZXJfc3lzdGVtIjoibG90dXMtbWFuYWdlIiwicGVyaW9kIjpudWxsLCJyZXBvcnRp"
            "bmdfY3VycmVuY3kiOiJVU0QiLCJ3aW5kb3ciOnsiZW5kX2RhdGUiOiIyMDI1LTAxLTMxIiwic3Rh"
            "cnRfZGF0ZSI6IjIwMjUtMDEtMzEifX0sInJvd19jb3VudCI6MSwic291cmNlX21ldGFkYXRhIjp7"
            "ImRhdGFfcXVhbGl0eV9zdGF0dXMiOiJDT01QTEVURSIsImZyZXNobmVzc19zdGF0dXMiOiJDVVJS"
            "RU5UIiwicGFnZSI6eyJuZXh0X3BhZ2VfdG9rZW4iOm51bGwsInJlcXVlc3Rfc2NvcGVfZmluZ2Vy"
            "cHJpbnQiOiJhY3R1YWwtc2NvcGUiLCJyZXR1cm5lZF9yb3dfY291bnQiOjEsInNuYXBzaG90X2Vw"
            "b2NoIjo3fSwicG9ydGZvbGlvX2lkIjoicG9ydGZvbGlvIiwicmVwb3J0aW5nX2N1cnJlbmN5Ijoi"
            "VVNEIiwicmVzb2x2ZWRfd2luZG93Ijp7ImVuZF9kYXRlIjoiMjAyNS0wMS0zMSIsInN0YXJ0X2Rh"
            "dGUiOiIyMDI1LTAxLTMxIn0sInNvdXJjZV9ldmlkZW5jZV9jdXJyZW50Ijp0cnVlLCJ0ZW5hbnRf"
            "aWQiOiJ0ZW5hbnQifX1dLCJzZWxlY3Rpb25fZGlnZXN0Ijoic2hhMjU2OjE5MTkwZTA0OGQ5YTM5"
            "OGUyNzEyMjlhNWJjZDBiYzA5YWI3NzJjNDlmMDkzOGY0MDFjOTJmYmI0MDlkN2ZiMjUifX19LCJz"
            "ZXJpYWxpemVyIjoicG9ydGZvbGlvLXRpbWVzZXJpZXMtZXhwb3J0OnJldGFpbmVkLWpzb246djEi"
            "fQ=="
        ),
    },
}
IngressRetainedCaptureVerifier = retained.IngressRetainedCaptureVerifier
SqlAlchemyPortfolioFinancialSourceCutReader = retained.SqlAlchemyPortfolioFinancialSourceCutReader
read_registry = read_tests.read_registry
registry_fixture = read_tests.registry_fixture
retained_service = read_tests.retained_service


def persisted_registry():
    _, query, cut, _ = registry_fixture(0)
    body = TypeAdapter(type(cut.header.manifest)).dump_python(cut.header.manifest, mode="json")
    identity = body.pop("identity")
    identity.pop("tenant_id")
    identity["registry_scope_id"] = identity.pop("scope_id")
    body.update(identity)
    raw = json.dumps(body, indent=2).encode()
    row = FinancialSourceCutRow(
        tenant_id="tenant",
        product_name="PortfolioHistoricalRegistry",
        source_system="producer",
        registry_scope_id="registry",
        source_cut_id="cut",
        revision=1,
        content_hash=cut.header.manifest.content_hash,
        raw_hash=hashlib.sha256(raw).hexdigest(),
        raw_bytes=raw,
        declaration=body,
        row_count=0,
        chunk_count=0,
        received_at=cut.header.received_at,
        receipt_job_id=cut.header.receipt_job_id,
    )
    job = SimpleNamespace(
        status="completed",
        completed_at=cut.header.completed_at,
        endpoint="/ingest/portfolio-historical-registry-cuts",
        entity_type="portfolio_historical_registry",
        accepted_count=1,
    )
    work = SimpleNamespace(
        status="COMPLETED",
        receipt_job_id=row.receipt_job_id,
        content_hash=row.content_hash,
        checkpoint={},
    )
    return query, row, job, work


@pytest.mark.asyncio
async def test_exact_native_terminal_receipt_and_raw_typed_scope_fences():
    query, row, job, work = persisted_registry()
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[row, job, work]))
    cut = await SqlAlchemyPortfolioFinancialSourceCutReader(session).cut(
        "tenant", row.product_name, query
    )
    assert cut.header.completed_at == job.completed_at
    assert cut.header.receipt_job_id == row.receipt_job_id
    for call in session.scalar.call_args_list:
        statement = call.args[0].compile(dialect=postgresql.dialect())
        assert "tenant_id" in str(statement) and "tenant" in statement.params.values()
    manifest_statement = (
        session.scalar.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
    )
    assert {"producer", "registry", "cut", 1, row.product_name} <= set(
        manifest_statement.params.values()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["pending", "failed", "work", "raw", "typed", "receipt_kind"])
async def test_incomplete_corrupt_or_foreign_receipt_cannot_be_complete_empty(drift):
    query, row, job, work = persisted_registry()
    if drift in {"pending", "failed"}:
        job.status = drift
    elif drift == "work":
        work.status = "PENDING"
    elif drift == "raw":
        row.raw_bytes += b" "
    elif drift == "typed":
        row.content_hash = "b" * 64
    else:
        job.entity_type = "portfolio_financial_source_cut"
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[row, job, work]))
    with pytest.raises(ValueError):
        await SqlAlchemyPortfolioFinancialSourceCutReader(session).cut(
            "tenant", row.product_name, query
        )


@pytest.mark.asyncio
async def test_absent_is_distinct_from_empty_completed_manifest():
    query, row, _, _ = persisted_registry()
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    with pytest.raises(LookupError):
        await SqlAlchemyPortfolioFinancialSourceCutReader(session).cut(
            "tenant", row.product_name, query
        )


@pytest.mark.asyncio
async def test_selected_graph_rehydrates_by_exact_tenant_and_portfolio_without_unrelated_rows():
    from portfolio_common.portfolio_financial_source_cut_models import FinancialSourceInputRow

    _, query, cut, expected = read_tests.financial_fixture()
    row = FinancialSourceInputRow(
        tenant_id="tenant",
        product_name="PortfolioFinancialSourceCut",
        source_system=query.source_system,
        registry_scope_id=query.registry_scope_id,
        source_cut_id=query.source_cut_id,
        revision=query.revision,
        portfolio_id=query.portfolio_id,
        chunk_index=0,
        content_hash=expected.input_content_hash,
        declaration=expected.declaration.model_dump(mode="json"),
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    result = await SqlAlchemyPortfolioFinancialSourceCutReader(session).selected_input(
        "tenant", query, cut
    )
    assert result == expected
    assert session.scalar.call_count == 1
    statement = session.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
    assert {
        "tenant",
        query.portfolio_id,
        query.source_cut_id,
        query.registry_scope_id,
        query.source_system,
        query.revision,
        "PortfolioFinancialSourceCut",
    } <= set(statement.params.values())
    row.content_hash = "f" * 64
    with pytest.raises(ValueError):
        await SqlAlchemyPortfolioFinancialSourceCutReader(session).selected_input(
            "tenant", query, cut
        )


class EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def close(self):
        pass


class ValueStream(EmptyStream):
    def __init__(self, values):
        self.values = iter(values)

    async def __anext__(self):
        try:
            return next(self.values)
        except StopIteration:
            raise StopAsyncIteration from None


def retained_native_records():
    from portfolio_common.domain.calculation_lineage import canonical_content_hash
    from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
    from portfolio_common.portfolio_financial_source_cut_models import FinancialSourceInputRow

    _, query, cut, selected = read_tests.financial_fixture()
    input_row = FinancialSourceInputRow(
        portfolio_id=query.portfolio_id,
        content_hash=selected.input_content_hash,
        declaration=selected.declaration.model_dump(mode="json"),
    )
    values, segments = [], []
    for selection in selected.declaration.selections:
        raw = b'{"synthetic":"opaque bytes; no native decoder claim"}'
        capture_id = canonical_content_hash(
            {
                "contract": "NativeSourceCaptureRequest:v1",
                "tenant": "tenant",
                "portfolio": query.portfolio_id,
                "product": selection.product_name,
                "version": selection.product_version,
                "selector": selection.selector_hash,
                "content": selection.content_hash,
                "receipt": selection.receipt_job_id,
                "revision": selection.source_revision,
                "page_index": 0,
            }
        )
        link = SimpleNamespace(role=selection.role.value, page_index=0)
        capture = SimpleNamespace(
            capture_id=capture_id,
            source_product=selection.product_name,
            product_version=selection.product_version,
            selector_hash=selection.selector_hash,
            typed_content_hash=selection.content_hash,
            raw_hash=hashlib.sha256(raw).hexdigest(),
            byte_count=len(raw),
            segment_count=1,
            serializer_id="synthetic-pending-catalog",
            mime_type="application/json",
            original_supplier_digest=None,
            original_supplier_reference=None,
            source_context=dict(
                completed_receipt_id=selection.receipt_job_id,
                source_revision=selection.source_revision,
                selector_json=json.dumps(selection.selector.model_dump(mode="json")),
                captured_at=cut.header.completed_at.isoformat(),
                schema_version="v1",
                snapshot_epoch="actual-synthetic-epoch"
                if selection.role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
                else None,
                request_scope=None,
                export_job_id=getattr(selection.selector, "export_job_id", None),
                refresh_of_job_id=None,
                returned_count=1,
                total_count=1,
                next_page_token=None,
            ),
        )
        values.append((link, capture))
        segments.append(ValueStream([SimpleNamespace(segment_index=0, raw_bytes=raw)]))
    return query, cut, input_row, values, segments


@pytest.mark.asyncio
async def test_retained_native_adapter_preserves_five_role_order_and_actual_nullable_context():
    from portfolio_common.domain.portfolio_financial_source_cuts import InputRole

    query, cut, input_row, values, segments = retained_native_records()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=input_row),
        stream=AsyncMock(return_value=ValueStream(values)),
        stream_scalars=AsyncMock(side_effect=segments),
    )
    rows = [
        row
        async for row in SqlAlchemyPortfolioFinancialSourceCutReader(session).captures(
            "tenant", query, cut
        )
    ]
    assert tuple(row.role for row in rows) == tuple(InputRole)
    assert rows[0].source_context.snapshot_epoch == "actual-synthetic-epoch"
    assert all(row.source_context.snapshot_epoch is None for row in rows[2:])
    assert all(row.source_context.request_scope is None for row in rows)
    statement = session.stream.call_args.args[0].compile(dialect=postgresql.dialect())
    assert {"tenant", query.portfolio_id} <= set(statement.params.values())
    assert "CASE" in str(statement) and "OFFSET" not in str(statement)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift", ["identity", "selector", "receipt", "epoch", "segments", "closure"]
)
async def test_native_capture_identity_context_root_and_population_drift_refuse(drift):
    query, cut, input_row, values, segments = retained_native_records()
    capture = values[0][1]
    if drift == "identity":
        capture.capture_id = "f" * 64
    elif drift == "selector":
        capture.selector_hash = "f" * 64
    elif drift == "receipt":
        capture.source_context["completed_receipt_id"] = "other"
    elif drift == "epoch":
        capture.source_context["snapshot_epoch"] = None
    elif drift == "segments":
        segments[0] = ValueStream([])
    else:
        capture.source_context["total_count"] = 2
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=input_row),
        stream=AsyncMock(return_value=ValueStream(values)),
        stream_scalars=AsyncMock(side_effect=segments),
    )
    with pytest.raises(ValueError):
        _ = [
            row
            async for row in SqlAlchemyPortfolioFinancialSourceCutReader(session).captures(
                "tenant", query, cut
            )
        ]


@pytest.mark.asyncio
async def test_ingress_capture_bytes_tags_receipt_and_roots_replay_with_source_off():
    query, row, job, work = persisted_registry()
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[row, job, work, row]),
        stream_scalars=AsyncMock(return_value=EmptyStream()),
    )
    reader = SqlAlchemyPortfolioFinancialSourceCutReader(session)
    query = query.model_copy(update={"view": "CAPTURES"})
    response = await read_registry(
        retained_service(reader, capture_verifier=IngressRetainedCaptureVerifier()), query
    )
    import base64

    capture = response.rows[0]
    assert base64.b64decode(capture.bytes_base64) == row.raw_bytes
    assert capture.raw_hash == row.raw_hash and capture.typed_content_hash == row.content_hash
    assert capture.source_context.receipt_job_id == row.receipt_job_id
    assert capture.source_context.captured_at == row.received_at
    assert capture.source_context.snapshot_epoch is None and capture.role is None
    assert capture.capture_id == ingress_capture_projection(row, chunk=False)["capture_id"]
    assert response.pagination.root_item_count == response.pagination.total_count == 1


@pytest.mark.asyncio
async def test_original_ingress_artifact_is_segmented_without_truncation_or_reserialization():
    import base64

    query, row, job, work = persisted_registry()
    row.raw_bytes += b" " * 524288
    row.raw_hash = hashlib.sha256(row.raw_bytes).hexdigest()
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[row, job, work, row, row, job, work, row]),
        stream_scalars=AsyncMock(side_effect=[EmptyStream(), EmptyStream()]),
    )
    service = retained_service(
        SqlAlchemyPortfolioFinancialSourceCutReader(session),
        capture_verifier=IngressRetainedCaptureVerifier(),
    )
    query = query.model_copy(
        update={"view": "CAPTURES", "page": query.page.model_copy(update={"page_size": 1})}
    )
    first = await read_registry(service, query)
    second = await read_registry(
        service,
        query.model_copy(
            update={
                "page": query.page.model_copy(
                    update={"page_token": first.pagination.next_page_token}
                )
            }
        ),
    )
    assert first.pagination.total_count == 2 and first.pagination.root_item_count == 1
    assert len(base64.b64decode(first.rows[0].bytes_base64)) == 524288
    assert (
        b"".join(base64.b64decode(row.bytes_base64) for row in (*first.rows, *second.rows))
        == row.raw_bytes
    )
    assert first.pagination.ordered_set_hash == second.pagination.ordered_set_hash


def test_ingress_decoder_refuses_unknown_tag_wrong_scope_and_nonfinite_raw():
    import base64
    import io

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    query, row, _, _ = persisted_registry()
    metadata = ingress_capture_projection(row, chunk=False)
    artifact = contracts.CaptureSegmentEvidence(
        **metadata,
        segment_index=0,
        segment_hash=row.raw_hash,
        bytes_base64=base64.b64encode(row.raw_bytes).decode(),
    )
    _, _, cut, _ = registry_fixture(0)
    verifier = IngressRetainedCaptureVerifier()
    verifier.verify(artifact, io.BytesIO(row.raw_bytes), identity=cut.header.manifest.identity)
    with pytest.raises(ValueError, match="catalog"):
        verifier.verify(
            artifact.model_copy(update={"serializer_id": "invented"}),
            io.BytesIO(row.raw_bytes),
            identity=cut.header.manifest.identity,
        )
    body = dict(row.declaration, source_system="foreign")
    with pytest.raises(ValueError, match="scope"):
        verifier.verify(
            artifact, io.BytesIO(json.dumps(body).encode()), identity=cut.header.manifest.identity
        )
    with pytest.raises(ValueError, match="nonfinite"):
        verifier.verify(artifact, io.BytesIO(b'{"bad":NaN}'), identity=cut.header.manifest.identity)


def native_payloads():
    """Three exact producer vectors and two explicitly derived synthetic role controls."""
    import base64
    from copy import deepcopy

    from portfolio_common.analytics_export_source_identity import export_source_selection_digest
    from portfolio_common.domain.portfolio_source_observations import FundingInvestmentObservation

    values = {}
    for role, vector in NATIVE_CAPTURE_VECTORS.items():
        raw = base64.b64decode(vector["bytes_base64"], validate=True)
        assert hashlib.sha256(raw).hexdigest() == vector["raw_sha256"]
        values[role] = json.loads(raw)["payload"]
    readiness = deepcopy(values["CASH"])
    readiness["fact"] = dict(envelope=readiness["fact"]["envelope"], funded=False, invested=None)
    readiness["receipt"].update(
        endpoint="/ingest/portfolio-funding-investment-observations",
        entity_type="portfolio_funding_investment_observation",
        job_id="synthetic-readiness-receipt",
    )
    fact = TypeAdapter(FundingInvestmentObservation).validate_json(
        json.dumps(readiness["fact"]), strict=True
    )
    readiness["content_hash"] = readiness["observation_id"] = fact.content_hash
    values["READINESS"] = readiness
    prior = deepcopy(values["MONTH_END_ASSETS"])
    prior["receipt"]["job_id"] = prior["result"]["job_id"] = "synthetic-prior-export"
    prior["request"]["portfolio_timeseries_request"]["window"] = dict(
        start_date="2024-12-31", end_date="2024-12-31"
    )
    prior["result"]["data"][0]["valuation_date"] = "2024-12-31"
    page = prior["result"]["source_evidence"]["pages"][0]
    page["requested_scope"]["window"] = dict(start_date="2024-12-31", end_date="2024-12-31")
    page["source_metadata"]["resolved_window"] = dict(
        start_date="2024-12-31", end_date="2024-12-31"
    )
    evidence = prior["result"]["source_evidence"]
    evidence["selection_digest"] = export_source_selection_digest(prior["result"]["data"], evidence)
    values["PRIOR_ASSETS"] = prior
    return values


def native_vector_fixture(*, large=False):
    """Synthetic graph/capture fixture; no database, acquisition or native receipt proof."""
    import base64

    from portfolio_common.analytics_export_source_identity import export_source_selection_digest
    from portfolio_common.domain.calculation_lineage import canonical_content_hash
    from portfolio_common.domain.portfolio_financial_source_cuts import (
        InputRole,
        source_product_bytes,
    )
    from portfolio_common.portfolio_financial_source_cut_admission import (
        FinancialInput,
        financial_input_from_payload,
    )
    from portfolio_common.portfolio_financial_source_cut_models import (
        NATIVE_CAPTURE_SERIALIZERS,
        native_capture_typed_root,
    )

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    payloads = native_payloads()
    if large:
        payload = payloads["MONTH_END_ASSETS"]
        payload["result"]["data"][0]["synthetic_unicode_stress"] = "口座é" * 40000
        evidence = payload["result"]["source_evidence"]
        evidence["selection_digest"] = export_source_selection_digest(
            payload["result"]["data"], evidence
        )
    _, query, cut, original = read_tests.financial_fixture()
    declaration = original.declaration.model_dump(mode="json")
    declaration["portfolio_id"] = "portfolio"
    segments, selections = [], []
    for role in InputRole:
        payload, tag = payloads[role.value], NATIVE_CAPTURE_SERIALIZERS[role.value]
        raw = source_product_bytes(payload, serializer=tag)
        root = native_capture_typed_root(tag, payload)
        if role.value in NATIVE_CAPTURE_VECTORS and not (
            large and role is InputRole.MONTH_END_ASSETS
        ):
            vector = NATIVE_CAPTURE_VECTORS[role.value]
            assert raw == base64.b64decode(vector["bytes_base64"])
            assert root == vector["typed_root"]
        selector = native_vector_selector(role, payload, root)
        receipt = payload["receipt"]["job_id"]
        revision = (
            receipt
            if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
            else str(
                payload["cut"]["cut_revision"]
                if role is InputRole.FLOWS
                else payload["fact"]["envelope"]["source_revision"]
            )
        )
        selection = dict(
            role=role.value,
            product_name=payload["product_name"],
            product_version="v1",
            selector=selector,
            selector_hash=canonical_content_hash(selector),
            content_hash=root,
            receipt_job_id=receipt,
            source_revision=revision,
        )
        selections.append(selection)
        segments.extend(native_vector_segments(role, payload, raw, root, selection, cut.header))
    declaration["selections"] = selections
    declaration = FinancialInput.model_validate(declaration)
    graph = financial_input_from_payload(
        cut.header.manifest.identity, declaration.model_dump(mode="json")
    )
    selected = contracts.FinancialInputEvidence(
        declaration=declaration,
        input_content_hash=canonical_content_hash(
            {
                "contract": "PortfolioFinancialSourceCutInput:v1",
                "selection": declaration.model_dump(mode="json"),
            }
        ),
        graph=graph,
        graph_content_hash=graph.content_hash,
    )
    query = query.model_copy(update={"portfolio_id": "portfolio", "view": "CAPTURES"})

    class Reader:
        async def cut(self, *args):
            return cut

        async def selected_input(self, *args):
            return selected

        async def captures(self, *args):
            for row in segments:
                yield row

    return Reader(), query, cut, selected, segments


def native_vector_selector(role, payload, root):
    from portfolio_common.domain.portfolio_financial_source_cuts import InputRole

    if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
        request = payload["request"]["portfolio_timeseries_request"]
        return dict(
            kind="VALUATION",
            as_of_date=request["as_of_date"],
            from_date=request["window"]["start_date"],
            to_date=request["window"]["end_date"],
            reporting_currency=request["reporting_currency"],
            consumer_system=request["consumer_system"],
            export_job_id=payload["receipt"]["job_id"],
            export_content_hash=root,
            refresh_of_job_id=payload["request"].get("refresh_of_job_id"),
        )
    if role is InputRole.FLOWS:
        cut = payload["cut"]
        return dict(
            kind="FLOWS",
            source_system=cut["source_system"],
            source_cut_id=cut["source_cut_id"],
            cut_revision=cut["cut_revision"],
            manifest_hash=root,
            from_date=cut["coverage_from"],
            to_date=cut["coverage_to"],
            currency=cut["currency"],
        )
    envelope = payload["fact"]["envelope"]
    return dict(
        kind=role.value,
        as_of_date="2025-01-31",
        producer_id=envelope["producer_id"],
        source_record_id=envelope["source_record_id"],
        observation_id=root,
        content_hash=root,
        source_cut_id=envelope["source_cut_id"],
        source_version=envelope["source_revision"],
    )


def native_vector_segments(role, payload, raw, root, selection, header):
    import base64

    from portfolio_common.domain.calculation_lineage import canonical_content_hash
    from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
    from portfolio_common.portfolio_financial_source_cut_models import NATIVE_CAPTURE_SERIALIZERS

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    valuation = role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
    paging = (
        payload["result"]["source_evidence"]["pages"][0]["source_metadata"]["page"]
        if valuation
        else None
    )
    count = (
        payload["receipt"]["result_row_count"]
        if valuation
        else (
            len(payload["events"]) + len(payload["dependencies"]) if role is InputRole.FLOWS else 1
        )
    )
    capture_id = canonical_content_hash(
        {
            "contract": "NativeSourceCaptureRequest:v1",
            "tenant": "tenant",
            "portfolio": "portfolio",
            "product": selection["product_name"],
            "version": "v1",
            "selector": selection["selector_hash"],
            "content": root,
            "receipt": selection["receipt_job_id"],
            "revision": selection["source_revision"],
            "page_index": 0,
        }
    )
    metadata = dict(
        capture_id=capture_id,
        role=role,
        source_page_index=0,
        source_product=selection["product_name"],
        product_version="v1",
        selector_hash=selection["selector_hash"],
        typed_content_hash=root,
        raw_hash=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        segment_count=(len(raw) + 524287) // 524288,
        serializer_id=NATIVE_CAPTURE_SERIALIZERS[role.value],
        schema_version="v1",
        mime_type="application/json",
        source_context=dict(
            capture_origin="ACQUIRED_NATIVE_DTO",
            captured_at=header.completed_at,
            snapshot_epoch=str(paging["snapshot_epoch"]) if valuation else None,
            request_scope=paging["request_scope_fingerprint"] if valuation else None,
            receipt_job_id=selection["receipt_job_id"],
            source_revision=selection["source_revision"],
            selector_json=json.dumps(selection["selector"]),
            export_job_id=payload["receipt"]["job_id"] if valuation else None,
            refresh_of_job_id=payload["request"].get("refresh_of_job_id") if valuation else None,
            returned_count=count,
            total_count=count,
            next_page_token=None,
        ),
    )
    return [
        contracts.CaptureSegmentEvidence(
            **metadata,
            segment_index=index,
            segment_hash=hashlib.sha256(chunk).hexdigest(),
            bytes_base64=base64.b64encode(chunk).decode(),
        )
        for index in range(metadata["segment_count"])
        for chunk in [raw[index * 524288 : (index + 1) * 524288]]
    ]


@pytest.mark.parametrize("role", ["CASH", "READINESS", "FLOWS", "PRIOR_ASSETS", "MONTH_END_ASSETS"])
def test_admitted_native_catalog_decodes_complete_role_and_preserves_original_vector_bytes(role):
    import base64
    import io

    _, _, cut, selected, rows = native_vector_fixture()
    artifact = next(row for row in rows if row.role == role)
    raw = base64.b64decode(artifact.bytes_base64)
    retained.RetainedSourceCaptureVerifier().verify(
        artifact, io.BytesIO(raw), identity=cut.header.manifest.identity, financial_input=selected
    )
    payload = json.loads(raw)["payload"]
    if role in NATIVE_CAPTURE_VECTORS:
        assert raw == base64.b64decode(NATIVE_CAPTURE_VECTORS[role]["bytes_base64"])
        assert artifact.typed_content_hash == NATIVE_CAPTURE_VECTORS[role]["typed_root"]
    if role == "CASH":
        assert payload["fact"]["settled"] == "0.00" and payload["fact"]["available"] is None
    if role == "READINESS":
        assert payload["fact"]["funded"] is False and payload["fact"]["invested"] is None
    if role in ("CASH", "READINESS", "FLOWS"):
        assert (
            artifact.source_context.snapshot_epoch is artifact.source_context.request_scope is None
        )


def recaptured_artifact(artifact, raw):
    """Synthetic corruption control retaining selection pins while rebinding changed raw bytes."""
    import base64

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    return contracts.CaptureSegmentEvidence(
        **artifact.model_dump(
            exclude={
                "raw_hash",
                "byte_count",
                "segment_count",
                "segment_index",
                "segment_hash",
                "bytes_base64",
            }
        ),
        raw_hash=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        segment_count=1,
        segment_index=0,
        segment_hash=hashlib.sha256(raw).hexdigest(),
        bytes_base64=base64.b64encode(raw).decode(),
    )


@pytest.mark.parametrize(
    "role,drift",
    [
        ("CASH", "unknown_serializer"),
        ("CASH", "wrong_role_serializer"),
        ("CASH", "schema"),
        ("CASH", "mime"),
        ("CASH", "wrapper_serializer"),
        ("CASH", "wrapper_extra"),
        ("CASH", "wrapper_duplicate"),
        ("CASH", "noncanonical"),
        ("CASH", "utf16"),
        ("CASH", "raw_root"),
        ("CASH", "typed_root"),
        ("CASH", "selector"),
        ("CASH", "fact_amount"),
        ("CASH", "decimal_number"),
        ("CASH", "missing_envelope_field"),
        ("CASH", "payload_extra"),
        ("CASH", "receipt_tenant"),
        ("CASH", "receipt_status"),
        ("CASH", "receipt_family"),
        ("CASH", "receipt_count_bool"),
        ("CASH", "receipt_naive_time"),
        ("CASH", "invented_epoch"),
        ("READINESS", "strict_boolean"),
        ("FLOWS", "missing_event"),
        ("FLOWS", "event_receipt_family"),
        ("FLOWS", "invented_scope"),
        ("MONTH_END_ASSETS", "missing_epoch"),
        ("MONTH_END_ASSETS", "epoch"),
        ("MONTH_END_ASSETS", "request_scope"),
        ("MONTH_END_ASSETS", "export_context"),
        ("MONTH_END_ASSETS", "export_revision"),
        ("MONTH_END_ASSETS", "refresh_context"),
        ("MONTH_END_ASSETS", "traversal"),
        ("MONTH_END_ASSETS", "result_count_bool"),
        ("MONTH_END_ASSETS", "receipt_job"),
        ("MONTH_END_ASSETS", "request_portfolio"),
    ],
)
def test_native_catalog_refuses_wrapper_typed_receipt_selector_and_actual_context_drift(
    role, drift
):
    import base64
    import io

    from portfolio_common.domain.portfolio_financial_source_cuts import source_product_bytes

    _, _, cut, selected, rows = native_vector_fixture()
    artifact = next(row for row in rows if row.role == role)
    raw = base64.b64decode(artifact.bytes_base64)
    wrapper = json.loads(raw)
    payload = wrapper["payload"]
    changes = {
        "unknown_serializer": {"serializer_id": "unknown-native-catalog"},
        "wrong_role_serializer": {"serializer_id": "portfolio-funding-investment:domain-json:v1"},
        "schema": {"schema_version": "v2"},
        "mime": {"mime_type": "application/x-ndjson"},
        "raw_root": {"raw_hash": "f" * 64},
        "typed_root": {"typed_content_hash": "f" * 64},
    }
    contexts = {
        "selector": {"selector_json": "{}"},
        "invented_epoch": {"snapshot_epoch": "7"},
        "invented_scope": {"request_scope": "invented"},
        "missing_epoch": {"snapshot_epoch": None},
        "epoch": {"snapshot_epoch": "8"},
        "request_scope": {"request_scope": "foreign-scope"},
        "export_context": {"export_job_id": "foreign-export"},
        "export_revision": {"source_revision": "7"},
        "refresh_context": {"refresh_of_job_id": "foreign-original"},
    }
    if drift in changes:
        artifact = artifact.model_copy(update=changes[drift])
    elif drift in contexts:
        artifact = artifact.model_copy(
            update={"source_context": artifact.source_context.model_copy(update=contexts[drift])}
        )
    elif drift == "wrapper_duplicate":
        raw = raw.replace(b'{"payload":', b'{"serializer":"duplicate","payload":', 1)
    elif drift == "noncanonical":
        raw = b" " + raw
    elif drift == "utf16":
        raw = raw.decode().encode("utf-16")
    else:
        mutate_native_wrapper(wrapper, drift)
        raw = (
            source_product_bytes(payload, serializer=wrapper["serializer"])
            if set(wrapper) == {"payload", "serializer"}
            else json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode()
        )
    if drift not in changes and drift not in contexts:
        artifact = recaptured_artifact(artifact, raw)
    with pytest.raises(ValueError):
        retained.RetainedSourceCaptureVerifier().verify(
            artifact,
            io.BytesIO(raw),
            identity=cut.header.manifest.identity,
            financial_input=selected,
        )


def mutate_native_wrapper(wrapper, drift):
    payload = wrapper["payload"]
    if drift == "wrapper_serializer":
        wrapper["serializer"] = "portfolio-funding-investment:domain-json:v1"
    elif drift == "wrapper_extra":
        wrapper["extra"] = True
    elif drift == "fact_amount":
        payload["fact"]["settled"] = "1.00"
    elif drift == "decimal_number":
        payload["fact"]["settled"] = 0
    elif drift == "missing_envelope_field":
        payload["fact"]["envelope"].pop("expected_head_hash")
    elif drift == "payload_extra":
        payload["extra"] = True
    elif drift == "strict_boolean":
        payload["fact"]["funded"] = 0
    elif drift == "missing_event":
        payload["events"] = []
    elif drift == "event_receipt_family":
        payload["events"][0]["receipt"]["entity_type"] = "portfolio_cash_availability_observation"
    elif drift == "traversal":
        payload["result"]["source_evidence"]["pages"][0]["source_metadata"]["page"][
            "next_page_token"
        ] = "unfinished"
    elif drift == "result_count_bool":
        payload["receipt"]["result_row_count"] = True
    elif drift == "request_portfolio":
        payload["request"]["portfolio_id"] = "foreign-portfolio"
    else:
        field, value = {
            "receipt_tenant": ("tenant_id", "foreign"),
            "receipt_status": ("status", "accepted"),
            "receipt_family": ("entity_type", "portfolio_funding_investment_observation"),
            "receipt_count_bool": ("accepted_count", True),
            "receipt_naive_time": ("completed_at", "2026-10-16T00:00:00"),
            "receipt_job": ("job_id", "foreign-export"),
        }[drift]
        payload["receipt"][field] = value


@pytest.mark.asyncio
async def test_five_role_native_source_off_replay_retains_vectors_segments_and_independent_roots():
    import base64

    from portfolio_common.domain.portfolio_financial_source_cuts import InputRole

    reader, query, _, selected, rows = native_vector_fixture(large=True)
    service = retained_service(reader, capture_verifier=retained.RetainedSourceCaptureVerifier())
    query = query.model_copy(update={"page": query.page.model_copy(update={"page_size": 2})})
    original_query = query
    seen, roots = [], set()
    while True:
        response = await service.query(
            tenant_id="tenant",
            service_identity="lotus-manage",
            product="PortfolioFinancialSourceCut",
            request=query,
        )
        seen.extend(response.rows)
        roots.add(response.pagination.ordered_set_hash)
        assert response.pagination.root_item_count == 5 and response.pagination.total_count == 6
        assert len(response.model_dump_json().encode()) <= service.response_byte_budget
        assert (
            response.authoritative_use_available is False
            and response.qualification == "UNQUALIFIED"
        )
        if response.pagination.next_page_token is None:
            break
        query = query.model_copy(
            update={
                "page": query.page.model_copy(
                    update={"page_token": response.pagination.next_page_token}
                )
            }
        )
    assert seen == rows and len(roots) == 1
    assert [row.role for row in seen] == [
        InputRole.PRIOR_ASSETS,
        InputRole.MONTH_END_ASSETS,
        InputRole.MONTH_END_ASSETS,
        InputRole.CASH,
        InputRole.READINESS,
        InputRole.FLOWS,
    ]
    assert all(len(base64.b64decode(row.bytes_base64)) <= 524288 for row in seen)
    replay = await service.query(
        tenant_id="tenant",
        service_identity="lotus-manage",
        product="PortfolioFinancialSourceCut",
        request=original_query,
    )
    assert replay.rows == tuple(rows[:2]) and replay.pagination.ordered_set_hash in roots
    assert selected.graph_content_hash != original_query.content_hash


def rebind_synthetic_role(selected, artifact, payload):
    """Adversarial synthetic declaration pins a recomputed root; semantics must still refuse."""
    from portfolio_common.analytics_export_source_identity import export_source_selection_digest
    from portfolio_common.domain.calculation_lineage import canonical_content_hash
    from portfolio_common.domain.portfolio_financial_source_cuts import (
        InputRole,
        source_product_bytes,
    )
    from portfolio_common.domain.portfolio_source_observations import CashAvailabilityObservation
    from portfolio_common.portfolio_financial_source_cut_admission import (
        FinancialInput,
        financial_input_from_payload,
    )
    from portfolio_common.portfolio_financial_source_cut_models import native_capture_typed_root

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    if artifact.role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
        evidence = payload["result"]["source_evidence"]
        evidence["selection_digest"] = export_source_selection_digest(
            payload["result"]["data"], evidence
        )
    else:
        model = CashAvailabilityObservation
        fact = TypeAdapter(model).validate_json(json.dumps(payload["fact"]), strict=True)
        payload["content_hash"] = payload["observation_id"] = fact.content_hash
    root = native_capture_typed_root(artifact.serializer_id, payload)
    body = selected.declaration.model_dump(mode="json")
    selection = next(value for value in body["selections"] if value["role"] == artifact.role)
    selection["content_hash"] = root
    if selection["selector"]["kind"] == "VALUATION":
        selection["selector"]["export_content_hash"] = root
    else:
        selection["selector"]["content_hash"] = selection["selector"]["observation_id"] = root
    selection["selector_hash"] = canonical_content_hash(selection["selector"])
    declaration = FinancialInput.model_validate(body)
    graph = financial_input_from_payload(
        selected.graph.identity, declaration.model_dump(mode="json")
    )
    changed = contracts.FinancialInputEvidence(
        declaration=declaration,
        input_content_hash=canonical_content_hash(
            {
                "contract": "PortfolioFinancialSourceCutInput:v1",
                "selection": declaration.model_dump(mode="json"),
            }
        ),
        graph=graph,
        graph_content_hash=graph.content_hash,
    )
    selection = next(value for value in declaration.selections if value.role == artifact.role)
    raw = source_product_bytes(payload, serializer=artifact.serializer_id)
    artifact = recaptured_artifact(artifact, raw).model_copy(
        update={
            "typed_content_hash": root,
            "selector_hash": selection.selector_hash,
            "capture_id": retained.native_capture_identity(
                graph.identity.tenant_id, graph.portfolio_id, selection, 0
            ),
            "source_context": artifact.source_context.model_copy(
                update={"selector_json": json.dumps(selection.selector.model_dump(mode="json"))}
            ),
        }
    )
    return changed, artifact, raw


def test_matching_typed_hash_does_not_authorize_foreign_selected_portfolio():
    import base64
    import io

    _, _, cut, selected, rows = native_vector_fixture()
    artifact = next(row for row in rows if row.role == "CASH")
    payload = json.loads(base64.b64decode(artifact.bytes_base64))["payload"]
    payload["fact"]["envelope"]["portfolio_id"] = "foreign-portfolio"
    changed, artifact, raw = rebind_synthetic_role(selected, artifact, payload)
    with pytest.raises(ValueError, match="source scope"):
        retained.RetainedSourceCaptureVerifier().verify(
            artifact,
            io.BytesIO(raw),
            identity=cut.header.manifest.identity,
            financial_input=changed,
        )


@pytest.mark.parametrize(
    "drift",
    ["tenant", "epoch", "scope", "count", "page_number", "consumer", "request_asof", "mixed_epoch"],
)
def test_valuation_matching_digest_still_requires_actual_scope_epoch_and_dense_complete_pages(
    drift,
):
    import base64
    import io
    from copy import deepcopy

    _, _, cut, selected, rows = native_vector_fixture()
    artifact = next(row for row in rows if row.role == "MONTH_END_ASSETS")
    payload = json.loads(base64.b64decode(artifact.bytes_base64))["payload"]
    page = payload["result"]["source_evidence"]["pages"][0]
    if drift == "tenant":
        page["source_metadata"]["tenant_id"] = "foreign"
    elif drift == "epoch":
        page["source_metadata"]["page"]["snapshot_epoch"] = 8
    elif drift == "scope":
        page["source_metadata"]["page"]["request_scope_fingerprint"] = "foreign"
    elif drift == "count":
        page["row_count"] = page["source_metadata"]["page"]["returned_row_count"] = 2
    elif drift == "page_number":
        page["page_number"] = 2
    elif drift == "consumer":
        page["requested_scope"]["consumer_system"] = "foreign"
    elif drift == "request_asof":
        payload["request"]["portfolio_timeseries_request"]["as_of_date"] = "2025-01-30"
    else:
        second = deepcopy(page)
        page["source_metadata"]["page"]["next_page_token"] = "synthetic-cursor"
        second["page_number"] = 2
        second["row_count"] = second["source_metadata"]["page"]["returned_row_count"] = 0
        second["source_metadata"]["page"]["snapshot_epoch"] = 8
        payload["result"]["source_evidence"]["pages"].append(second)
    changed, artifact, raw = rebind_synthetic_role(selected, artifact, payload)
    with pytest.raises(ValueError, match="valuation"):
        retained.RetainedSourceCaptureVerifier().verify(
            artifact,
            io.BytesIO(raw),
            identity=cut.header.manifest.identity,
            financial_input=changed,
        )
