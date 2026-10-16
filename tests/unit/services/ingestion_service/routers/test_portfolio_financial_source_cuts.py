"""Registered typed collections and actual streamed admission budgets, without native SQL proof."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var
from starlette.requests import Request

from src.services.ingestion_service.app.dependencies import (
    get_portfolio_financial_source_cut_commands,
)
from src.services.ingestion_service.app.enterprise_readiness import (
    NEUTRAL_SOURCE_WRITE_ENDPOINTS,
    buffer_neutral_source_body,
    ingestion_write_capability_rules,
)
from src.services.ingestion_service.app.main import app as registered_app
from src.services.ingestion_service.app.routers.portfolio_financial_source_cuts import (
    router,
    submit_source,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def chunk_payload():
    return dict(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        members=[],
        typed_content_hash=canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistryChunk:v1", "members": []}
        ),
    )


def collection_payload(collection):
    if collection == "portfolio-historical-registry-chunks":
        return chunk_payload()
    if collection == "portfolio-financial-source-cut-chunks":
        return {k: v for k, v in chunk_payload().items() if k != "members"} | dict(
            selections=[],
            typed_content_hash="5c37ccd67bf9a1c20846adeac8bbe5a62c663cf8c29e414bab59a714dfe05b8b",
        )
    payload = dict(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        definition_version="v1",
        coverage_from="2025-01-01",
        coverage_to="2025-01-31",
        calendar="SG",
        observed_at="2025-02-01T00:00:00Z",
        generated_at="2025-02-02T00:00:00Z",
        predecessor_hash=None,
        expected_head_hash=None,
        chunk_count=0,
        chunks_root="a" * 64,
    )
    if collection == "portfolio-historical-registry-cuts":
        return payload | dict(
            expected_population=dict(
                reference="expected", definition_version="v1", count=0, content_hash="a" * 64
            ),
            declared_coverage="COMPLETE",
            supplied_count=0,
            members_root="a" * 64,
        )
    return payload | dict(selection_count=0, selections_root="a" * 64)


def custody_test_app(commands, *, buffered=True):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_portfolio_financial_source_cut_commands] = lambda: commands

    @app.middleware("http")
    async def admitted_test_context(request, call_next):
        # Fixture substitutes verified enterprise admission, not source command grants.
        request.state.tenant_context = TenantContext(
            TenantId("tenant"), service_identity="producer", identity_verified=True
        )
        request.state.neutral_source_received_at = datetime.now(UTC)
        if buffered:
            refusal = await buffer_neutral_source_body(request)
            if refusal is not None:
                return refusal
        tokens = (
            correlation_id_var.set("corr"),
            request_id_var.set("request"),
            trace_id_var.set("trace"),
        )
        try:
            return await call_next(request)
        finally:
            trace_id_var.reset(tokens[2])
            request_id_var.reset(tokens[1])
            correlation_id_var.reset(tokens[0])

    return app


async def test_actual_app_registers_four_typed_collections_and_explicit_capabilities():
    schema = registered_app.openapi()
    rules = ingestion_write_capability_rules()
    for path in NEUTRAL_SOURCE_WRITE_ENDPOINTS:
        operation = schema["paths"][path]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]
        assert "202" in operation["responses"]
        assert rules["POST " + path] in {
            "ingestion.portfolio_historical_registries.write",
            "ingestion.portfolio_financial_source_cuts.write",
        }


async def test_http_typed_submission_preserves_original_raw_and_native_job():
    commands = SimpleNamespace(
        submit=AsyncMock(
            return_value=SimpleNamespace(
                job_id="original",
                entity_type="portfolio_historical_registry_chunk",
                accepted_count=0,
            )
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/portfolio-historical-registry-chunks",
            json=chunk_payload(),
            headers={"X-Idempotency-Key": "key"},
        )
    assert response.status_code == 202, response.text
    assert response.json()["job_id"] == "original"
    submitted = commands.submit.await_args.args[0]
    assert submitted.tenant_context.tenant_id_text == "tenant"
    assert submitted.received_at.utcoffset() is not None
    assert b'"source_cut_id":"cut"' in submitted.raw_bytes


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "tenant",
        "bool_revision",
        "oversize_chunked",
        "compression",
        "deep_json",
        "non_utf8",
    ],
)
async def test_hostile_http_body_has_no_command_effect(case):
    commands = SimpleNamespace(submit=AsyncMock())
    payload = chunk_payload()
    headers = {"X-Idempotency-Key": "key"}
    if case == "tenant":
        payload["tenant_id"] = "foreign"
    elif case == "bool_revision":
        payload["revision"] = True
    kwargs = {"json": payload}
    expected = 422
    if case == "duplicate":
        import json

        kwargs = {
            "content": json.dumps(payload).replace('"revision": 1', '"revision": 1, "revision": 1')
        }
    elif case == "deep_json":
        kwargs = {"content": "[" * 1500 + "0" + "]" * 1500}
    elif case == "non_utf8":
        kwargs = {"content": b"\xff\xfe"}
    elif case == "oversize_chunked":

        async def chunks():
            yield b" " * 524288
            yield b" " * 524288
            yield b" "

        kwargs = {"content": chunks()}
        expected = 413
    elif case == "compression":
        headers["Content-Encoding"] = "gzip"
        expected = 415
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/portfolio-historical-registry-chunks", headers=headers, **kwargs
        )
    assert response.status_code == expected, response.text
    commands.submit.assert_not_awaited()


@pytest.mark.parametrize(
    ("collection", "entity", "dto_name"),
    [
        (
            "portfolio-historical-registry-chunks",
            "portfolio_historical_registry_chunk",
            "RegistryChunkInput",
        ),
        (
            "portfolio-historical-registry-cuts",
            "portfolio_historical_registry_cut",
            "RegistrySealInput",
        ),
        (
            "portfolio-financial-source-cut-chunks",
            "portfolio_financial_source_cut_chunk",
            "FinancialChunkInput",
        ),
        ("portfolio-financial-source-cuts", "portfolio_financial_source_cut", "FinancialSealInput"),
    ],
)
async def test_all_typed_collections_acknowledge_exact_native_receipt(collection, entity, dto_name):
    commands = SimpleNamespace(
        submit=AsyncMock(
            return_value=SimpleNamespace(
                job_id="retained-native-job",
                entity_type=entity,
                accepted_count=0,
            )
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/" + collection,
            json=collection_payload(collection),
            headers={"X-Idempotency-Key": "original-key"},
        )
    assert response.status_code == 202, response.text
    assert response.json() == dict(
        message="Source custody command retained; poll the original native job for completion.",
        entity_type=entity,
        accepted_count=0,
        job_id="retained-native-job",
        idempotency_key="original-key",
        correlation_id="corr",
        request_id="request",
        trace_id="trace",
    )
    commands.submit.assert_awaited_once()
    submission = commands.submit.await_args.args[0]
    assert type(submission.request).__name__ == dto_name
    assert submission.idempotency_key == "original-key"


async def test_missing_idempotency_refuses_before_command():
    commands = SimpleNamespace(submit=AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/portfolio-historical-registry-chunks", json=chunk_payload()
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "INGESTION_IDEMPOTENCY_KEY_REQUIRED"}
    commands.submit.assert_not_awaited()


@pytest.mark.parametrize(
    "collection",
    [
        "portfolio-historical-registry-chunks",
        "portfolio-financial-source-cut-chunks",
    ],
)
async def test_typed_chunk_root_substitution_refuses_before_command(collection):
    commands = SimpleNamespace(submit=AsyncMock())
    payload = collection_payload(collection) | {"typed_content_hash": "a" * 64}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/" + collection, json=payload, headers={"X-Idempotency-Key": "key"}
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "value_error"
    assert "chunk typed hash mismatch" in response.json()["detail"][0]["msg"]
    commands.submit.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (PermissionError("private grant context"), 403, "SOURCE_REGISTRY_ADMISSION_REQUIRED"),
        (ObservationConflict("INGESTION_MODE_BLOCKS_WRITES"), 503, "INGESTION_MODE_BLOCKS_WRITES"),
        (
            ObservationConflict("INGESTION_RATE_LIMIT_EXCEEDED"),
            429,
            "INGESTION_RATE_LIMIT_EXCEEDED",
        ),
        (ObservationConflict("SOURCE_CUT_HEAD_CONFLICT"), 409, "SOURCE_CUT_HEAD_CONFLICT"),
    ],
)
async def test_command_refusals_map_to_safe_exact_http_error(error, status, detail):
    commands = SimpleNamespace(submit=AsyncMock(side_effect=error))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands)), base_url="http://test"
    ) as client:
        response = await client.post(
            "/ingest/portfolio-historical-registry-chunks",
            json=chunk_payload(),
            headers={"X-Idempotency-Key": "key"},
        )
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    commands.submit.assert_awaited_once()


@pytest.mark.parametrize("raw", [b'{"revision":1,"revision":2}', b"\xff", b'{"broken":'])
async def test_unbuffered_closed_parser_fallback_refuses_before_command(raw):
    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/test",
            "headers": [(b"x-idempotency-key", b"key")],
        },
        receive,
    )
    request.state.neutral_source_received_at = datetime.now(UTC)
    commands = SimpleNamespace(submit=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await submit_source(request, object(), commands)
    assert error.value.status_code == 422
    assert error.value.detail == "SOURCE_CLOSED_JSON_REQUIRED"
    commands.submit.assert_not_awaited()


@pytest.mark.parametrize("duplicate", [False, True], ids=["valid-fallback", "duplicate-fallback"])
async def test_closed_parser_fallback_through_typed_asgi_route(duplicate):
    import json

    commands = SimpleNamespace(
        submit=AsyncMock(
            return_value=SimpleNamespace(
                job_id="original",
                entity_type="portfolio_historical_registry_chunk",
                accepted_count=0,
            )
        )
    )
    raw = json.dumps(chunk_payload())
    if duplicate:
        raw = raw.replace('"revision": 1', '"revision": 1, "revision": 1')
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=custody_test_app(commands, buffered=False)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/ingest/portfolio-historical-registry-chunks",
            content=raw,
            headers={"X-Idempotency-Key": "key", "Content-Type": "application/json"},
        )
    if duplicate:
        assert response.status_code == 422
        assert response.json() == {"detail": "SOURCE_CLOSED_JSON_REQUIRED"}
        commands.submit.assert_not_awaited()
    else:
        assert response.status_code == 202, response.text
        commands.submit.assert_awaited_once()
        assert commands.submit.await_args.args[0].raw_bytes == raw.encode()
