from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)

from src.services.ingestion_service.app.dependencies import (
    get_portfolio_financial_source_cut_commands,
)
from src.services.ingestion_service.app.enterprise_readiness import (
    _required_capability,
    authorize_write_request,
    build_enterprise_audit_middleware,
    ingestion_write_capability_rules,
    load_capability_rules,
    validate_enterprise_runtime_config,
)
from src.services.ingestion_service.app.main import app


def _iter_routes(routes) -> list[object]:
    discovered: list[object] = []
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            discovered.extend(_iter_routes(original_router.routes))
            continue
        nested_routes = getattr(route, "routes", None)
        if nested_routes is not None:
            discovered.extend(_iter_routes(nested_routes))
            continue
        discovered.append(route)
    return discovered


def _enterprise_headers(capabilities: str) -> dict[str, str]:
    headers = {
        "X-Actor-Id": "actor-1",
        "X-Tenant-Id": "tenant-1",
        "X-Role": "ops",
        "X-Correlation-Id": "corr-1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": capabilities,
        "X-Enterprise-Auth-Key-Id": "kms-key-1",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        "auth-context-secret",
    )
    return headers


def _configure_auth_context_env(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")


def test_ingestion_default_rules_cover_all_ingestion_write_routes(monkeypatch) -> None:
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)
    rules = load_capability_rules()
    write_routes = {
        f"{method} {getattr(route, 'path', '')}"
        for route in _iter_routes(app.routes)
        for method in getattr(route, "methods", set())
        if method in {"POST", "PUT", "PATCH", "DELETE"}
        and (
            getattr(route, "path", "").startswith("/ingest/")
            or getattr(route, "path", "").startswith("/reprocess/")
        )
    }

    assert write_routes <= rules.keys()
    assert write_routes == ingestion_write_capability_rules().keys()


def test_ingestion_write_requires_route_capability(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)

    denied, denied_reason = authorize_write_request(
        "POST",
        "/ingest/portfolios",
        _enterprise_headers("ingestion.transactions.write"),
    )
    assert denied is False
    assert denied_reason == "missing_capability:ingestion.portfolios.write"

    allowed, allowed_reason = authorize_write_request(
        "POST",
        "/ingest/portfolios",
        _enterprise_headers("ingestion.portfolios.write"),
    )
    assert allowed is True
    assert allowed_reason is None


def test_ingestion_write_requires_service_identity_when_headers_present(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)
    headers = _enterprise_headers("ingestion.portfolios.write")
    headers.pop("X-Service-Identity")

    allowed, reason = authorize_write_request("POST", "/ingest/portfolios", headers)

    assert allowed is False
    assert reason == "missing_service_identity"


def test_ingestion_reference_routes_share_reference_data_capability() -> None:
    assert (
        _required_capability("POST", "/ingest/benchmark-assignments")
        == "ingestion.reference_data.write"
    )
    assert (
        _required_capability("POST", "/ingest/reference/cash-accounts")
        == "ingestion.reference_data.write"
    )


def test_fixed_income_book_cost_authority_requires_dedicated_capability() -> None:
    assert (
        _required_capability("POST", "/ingest/fixed-income-book-cost-authorities")
        == "ingestion.fixed_income_book_cost.authority.write"
    )


def test_corporate_action_manifest_requires_dedicated_capability() -> None:
    assert (
        _required_capability("POST", "/ingest/corporate-action-manifests")
        == "ingestion.corporate_actions.manifest.write"
    )


def test_validate_ingestion_runtime_accepts_default_capability_rules(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    issues = validate_enterprise_runtime_config()

    assert "missing_capability_rules" not in issues
    assert "missing_primary_key_id" not in issues


@pytest.mark.asyncio
async def test_ingestion_enterprise_middleware_emits_denied_write_audit(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/portfolios",
            "headers": [(b"content-length", b"0"), (b"x-tenant-id", b"tenant-test")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch("src.services.ingestion_service.app.enterprise_readiness.emit_audit_event") as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 403
    assert audit.call_args.kwargs["action"] == "DENY POST /ingest/portfolios"
    assert audit.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "status", "detail"),
    [
        ("valid", 202, None),
        ("malformed", 422, "SOURCE_CLOSED_JSON_REQUIRED"),
        ("encoding", 415, "source_body_encoding_unsupported"),
        ("stream_budget", 413, "source_body_byte_budget"),
        ("denied", 403, "authorization_policy_denied"),
    ],
)
async def test_registered_neutral_middleware_admission_and_body_replay(
    monkeypatch, case, status, detail
):
    # Run the registered chain: shared signature/tenant admission, neutral buffering,
    # typed FastAPI decoding, then the isolated command port. No lifespan/network.
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)
    capability = "ingestion.portfolio_historical_registries.write"
    headers = _enterprise_headers(
        "ingestion.transactions.write" if case == "denied" else capability
    )
    headers["X-Idempotency-Key"] = "retained-key"
    commands = SimpleNamespace(
        submit=AsyncMock(
            return_value=SimpleNamespace(
                job_id="native-receipt",
                entity_type="portfolio_historical_registry_chunk",
                accepted_count=0,
            )
        )
    )
    payload = dict(
        source_system="lotus-gateway",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        members=[],
        typed_content_hash=canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistryChunk:v1", "members": []}
        ),
    )
    kwargs = {"json": payload}
    if case == "malformed":
        kwargs = {"content": b'{"revision":1,"revision":2}'}
    elif case == "encoding":
        headers["Content-Encoding"] = "gzip"
    elif case == "stream_budget":

        async def chunks():
            yield b" " * 524288
            yield b" " * 524288
            yield b" "

        kwargs = {"content": chunks()}
    app.dependency_overrides[get_portfolio_financial_source_cut_commands] = lambda: commands
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/ingest/portfolio-historical-registry-chunks", headers=headers, **kwargs
            )
    finally:
        del app.dependency_overrides[get_portfolio_financial_source_cut_commands]
    assert response.status_code == status, response.text
    if case == "valid":
        commands.submit.assert_awaited_once()
        submitted = commands.submit.await_args.args[0]
        assert submitted.tenant_context.identity_verified is True
        assert submitted.tenant_context.tenant_id_text == "tenant-1"
        assert submitted.tenant_context.service_identity == "lotus-gateway"
        assert submitted.raw_bytes == response.request.content
        assert submitted.received_at.utcoffset().total_seconds() == 0
        assert response.json()["job_id"] == "native-receipt"
    else:
        assert response.json()["detail"] == detail
        commands.submit.assert_not_awaited()
        if case == "denied":
            assert response.json()["reason"] == "missing_capability:" + capability


@pytest.mark.asyncio
async def test_ingestion_middleware_bypasses_neutral_buffer_on_unrelated_route(monkeypatch):
    from fastapi import FastAPI

    from src.services.ingestion_service.app.enterprise_readiness import (
        build_ingestion_enterprise_audit_middleware,
    )

    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)
    isolated = FastAPI()
    isolated.middleware("http")(
        build_ingestion_enterprise_audit_middleware(max_write_payload_bytes_resolver=None)
    )

    @isolated.post("/ingest/portfolios")
    async def unrelated(request: Request):
        return {
            "body": (await request.body()).decode(),
            "neutral_buffered": hasattr(request.state, "neutral_source_closed_json"),
        }

    headers = _enterprise_headers("ingestion.portfolios.write")
    headers["Content-Encoding"] = "gzip"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=isolated), base_url="http://test"
    ) as client:
        response = await client.post("/ingest/portfolios", content=b"not-json", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"body": "not-json", "neutral_buffered": False}
