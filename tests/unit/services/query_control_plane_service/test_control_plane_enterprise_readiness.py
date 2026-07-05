import json
from time import time
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)
from portfolio_common.logging_utils import correlation_id_var

from src.services.query_control_plane_service.app.enterprise_readiness import (
    authorize_request,
    build_enterprise_audit_middleware,
    emit_audit_event,
    validate_enterprise_runtime_config,
)


def _configure_auth_context_env(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")


def _signed_enterprise_headers(capabilities: str) -> dict[str, str]:
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "analytics-service",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-performance",
        "X-Capabilities": capabilities,
        "X-Enterprise-Auth-Key-Id": "kms-key-1",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        "auth-context-secret",
    )
    return headers


def _headers_scope(headers: dict[str, str]) -> list[tuple[bytes, bytes]]:
    return [
        (key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()
    ]


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_omits_not_set_correlation_on_denied_audit(
    monkeypatch,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"0")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    token = correlation_id_var.set("<not-set>")
    try:
        with patch(
            "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
        ) as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 403
    assert audit.call_args.kwargs["correlation_id"] is None


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_omits_not_set_correlation_on_write_audit(
    monkeypatch,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"0")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    token = correlation_id_var.set("<not-set>")
    try:
        with patch(
            "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
        ) as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 200
    assert audit.call_args.kwargs["correlation_id"] is None


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_denies_read_without_headers_when_enabled(
    monkeypatch,
):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/integration/portfolios/PB1/analytics/reference",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch(
        "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
    ) as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 403
    assert (
        audit.call_args.kwargs["action"]
        == "DENY GET /integration/portfolios/PB1/analytics/reference"
    )
    assert audit.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")


@pytest.mark.asyncio
async def test_control_plane_enterprise_middleware_emits_read_audit_when_enabled(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_AUDIT_READS", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/integration/portfolios/PB1/analytics/reference",
        "headers": [
            (b"x-actor-id", b"a1"),
            (b"x-tenant-id", b"t1"),
            (b"x-role", b"analytics-service"),
            (b"x-correlation-id", b"c1"),
            (b"x-service-identity", b"lotus-performance"),
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch(
        "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
    ) as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 200
    assert audit.call_args.kwargs["action"] == (
        "GET /integration/portfolios/PB1/analytics/reference"
    )
    assert audit.call_args.kwargs["metadata"] == {
        "status_code": 200,
        "access_type": "read",
    }


def test_control_plane_emit_audit_event_preserves_none_correlation():
    with patch(
        "src.services.query_control_plane_service.app.enterprise_readiness.logger.info"
    ) as logger_info:
        emit_audit_event(
            action="WRITE /api/v1/integration",
            actor_id="actor-1",
            tenant_id="tenant-1",
            role="ops",
            correlation_id=None,
            metadata={"status_code": 202},
        )

    audit_payload = logger_info.call_args.kwargs["extra"]["audit"]
    assert audit_payload["correlation_id"] is None


def test_control_plane_authorize_request_enforces_read_capability_rules(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        json.dumps({"GET /integration/portfolios": "analytics.reference.read"}),
    )
    headers = _signed_enterprise_headers("positions.read")

    denied, denied_reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert denied is False
    assert denied_reason == "missing_capability:source_data.portfolio_analytics_reference.read"

    headers = _signed_enterprise_headers(
        "positions.read,source_data.portfolio_analytics_reference.read"
    )
    allowed, allowed_reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert allowed is True
    assert allowed_reason is None


def test_control_plane_authorize_request_requires_read_rule_when_strict(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    _configure_auth_context_env(monkeypatch)
    headers = _signed_enterprise_headers("")

    allowed, reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert allowed is False
    assert reason == "missing_capability:source_data.portfolio_analytics_reference.read"


def test_control_plane_authorize_request_uses_source_data_default_capability(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    _configure_auth_context_env(monkeypatch)
    headers = _signed_enterprise_headers("source_data.portfolio_analytics_reference.read")

    allowed, reason = authorize_request(
        "POST", "/integration/portfolios/PB1/analytics/reference", headers
    )

    assert allowed is True
    assert reason is None


def test_control_plane_runtime_config_accepts_source_data_default_rules(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    issues = validate_enterprise_runtime_config()

    assert "missing_capability_rules" not in issues
    assert "missing_primary_key_id" not in issues
