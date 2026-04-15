import json

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.logging_utils import correlation_id_var

from src.services.query_control_plane_service.app.enterprise_readiness import (
    authorize_request,
    build_enterprise_audit_middleware,
    emit_audit_event,
    validate_enterprise_runtime_config,
)


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
        from unittest.mock import patch

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
        from unittest.mock import patch

        with patch(
            "src.services.query_control_plane_service.app.enterprise_readiness.emit_audit_event"
        ) as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 200
    assert audit.call_args.kwargs["correlation_id"] is None


def test_control_plane_emit_audit_event_preserves_none_correlation():
    from unittest.mock import patch

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
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        json.dumps({"GET /integration/portfolios": "analytics.reference.read"}),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "analytics-service",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-performance",
        "X-Capabilities": "positions.read",
    }

    denied, denied_reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert denied is False
    assert denied_reason == "missing_capability:analytics.reference.read"

    headers["X-Capabilities"] = "positions.read,analytics.reference.read"
    allowed, allowed_reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert allowed is True
    assert allowed_reason is None


def test_control_plane_authorize_request_requires_read_rule_when_strict(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "analytics-service",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-performance",
    }

    allowed, reason = authorize_request(
        "GET", "/integration/portfolios/PB1/analytics/reference", headers
    )
    assert allowed is False
    assert reason == "missing_capability_rule"


def test_control_plane_runtime_config_reports_strict_read_rules_gap(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    issues = validate_enterprise_runtime_config()

    assert "missing_capability_rules" in issues
    assert "missing_primary_key_id" not in issues
