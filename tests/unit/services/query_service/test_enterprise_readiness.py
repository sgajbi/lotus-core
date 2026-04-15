import json
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.logging_utils import correlation_id_var

from src.services.query_service.app.enterprise_readiness import (
    _load_json_map,
    authorize_request,
    authorize_write_request,
    build_enterprise_audit_middleware,
    emit_audit_event,
    is_feature_enabled,
    load_feature_flags,
    redact_sensitive,
    validate_enterprise_runtime_config,
)


def test_feature_flags_tenant_role_resolution(monkeypatch):
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        json.dumps(
            {
                "query.advanced": {
                    "tenant-1": {"analyst": True, "*": False},
                    "*": {"*": False},
                }
            }
        ),
    )
    assert is_feature_enabled("query.advanced", "tenant-1", "analyst") is True
    assert is_feature_enabled("query.advanced", "tenant-1", "viewer") is False


def test_feature_flags_non_boolean_global_default_is_treated_as_disabled(monkeypatch):
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        json.dumps({"query.advanced": {"*": {"*": "disabled"}}}),
    )
    assert is_feature_enabled("query.advanced", "tenant-x", "ops") is False


def test_redaction_masks_sensitive_keys():
    payload = {"authorization": "Bearer abc", "nested": {"account_number": "1234", "ok": 1}}
    redacted = redact_sensitive(payload)
    assert redacted["authorization"] == "***REDACTED***"
    assert redacted["nested"]["account_number"] == "***REDACTED***"
    assert redacted["nested"]["ok"] == 1


def test_authorize_write_request_enforces_required_headers_when_enabled(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    allowed, reason = authorize_write_request("POST", "/transactions", {})
    assert allowed is False
    assert reason.startswith("missing_headers:")


def test_authorize_write_request_enforces_capability_rules(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        json.dumps({"POST /transactions": "transactions.write"}),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-core",
        "X-Capabilities": "transactions.read",
    }
    denied, denied_reason = authorize_write_request("POST", "/transactions/import", headers)
    assert denied is False
    assert denied_reason == "missing_capability:transactions.write"

    headers["X-Capabilities"] = "transactions.read,transactions.write"
    allowed, allowed_reason = authorize_write_request("POST", "/transactions/import", headers)
    assert allowed is True
    assert allowed_reason is None


def test_validate_enterprise_runtime_config_reports_rotation_issue(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "120")
    issues = validate_enterprise_runtime_config()
    assert "secret_rotation_days_out_of_range" in issues


def test_validate_enterprise_runtime_config_uses_default_when_rotation_not_numeric(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "not-a-number")
    issues = validate_enterprise_runtime_config()
    assert "secret_rotation_days_out_of_range" not in issues


def test_validate_enterprise_runtime_config_reports_invalid_payload_limit(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "0")
    issues = validate_enterprise_runtime_config()
    assert "max_write_payload_bytes_out_of_range" in issues


def test_validate_enterprise_runtime_config_reports_missing_primary_key(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.delenv("ENTERPRISE_PRIMARY_KEY_ID", raising=False)
    issues = validate_enterprise_runtime_config()
    assert "missing_primary_key_id" in issues


def test_validate_enterprise_runtime_config_raises_when_enforced(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_POLICY_VERSION", " ")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "true")
    with pytest.raises(RuntimeError, match="enterprise_runtime_config_invalid"):
        validate_enterprise_runtime_config()


def test_authorize_write_request_allows_non_write_method(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    allowed, reason = authorize_write_request("GET", "/integration", {})
    assert allowed is True
    assert reason is None


def test_redact_sensitive_handles_list_values():
    value = [{"token": "x"}, {"safe": 1}]
    redacted = redact_sensitive(value)
    assert redacted[0]["token"] == "***REDACTED***"
    assert redacted[1]["safe"] == 1


def test_load_json_map_returns_empty_on_invalid_json(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_FEATURE_FLAGS_JSON", "{invalid")
    assert _load_json_map("ENTERPRISE_FEATURE_FLAGS_JSON") == {}


def test_load_feature_flags_returns_empty_for_non_object_payload(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_FEATURE_FLAGS_JSON", "[]")
    assert load_feature_flags() == {}


def test_load_json_map_unknown_name_returns_empty_dict() -> None:
    assert _load_json_map("SOME_UNKNOWN_JSON_CONFIG") == {}


def test_authorize_write_request_requires_service_identity_when_headers_present(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
    }
    allowed, reason = authorize_write_request("POST", "/transactions", headers)
    assert allowed is False
    assert reason == "missing_service_identity"


def test_authorize_request_enforces_read_capability_rules_at_service_boundary(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        json.dumps({"GET /portfolios": "portfolios.read"}),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": "transactions.read",
    }

    denied, denied_reason = authorize_request("GET", "/portfolios/PB1", headers)
    assert denied is False
    assert denied_reason == "missing_capability:portfolios.read"

    headers["X-Capabilities"] = "transactions.read,portfolios.read"
    allowed, allowed_reason = authorize_request("GET", "/portfolios/PB1", headers)
    assert allowed is True
    assert allowed_reason is None


def test_authorize_request_requires_read_capability_rule_when_strict(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
    }

    allowed, reason = authorize_request("GET", "/portfolios/PB1", headers)
    assert allowed is False
    assert reason == "missing_capability_rule"


def test_validate_enterprise_runtime_config_reports_strict_read_rules_gap(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    issues = validate_enterprise_runtime_config()

    assert "missing_capability_rules" in issues
    assert "missing_primary_key_id" not in issues


@pytest.mark.asyncio
async def test_enterprise_middleware_denies_write_without_headers(monkeypatch):
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

    response = await middleware(request, _call_next)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_enterprise_middleware_allows_write_with_minimum_headers(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [
            (b"content-length", b"0"),
            (b"x-actor-id", b"a1"),
            (b"x-tenant-id", b"t1"),
            (b"x-role", b"ops"),
            (b"x-correlation-id", b"c1"),
            (b"x-service-identity", b"lotus-gateway"),
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_enterprise_middleware_denies_read_without_headers_when_enabled(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/portfolios/PB1",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch("src.services.query_service.app.enterprise_readiness.emit_audit_event") as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 403
    assert audit.call_args.kwargs["action"] == "DENY GET /api/v1/portfolios/PB1"
    assert audit.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")


@pytest.mark.asyncio
async def test_enterprise_middleware_emits_read_audit_when_enabled(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_AUDIT_READS", "true")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/portfolios/PB1",
        "headers": [
            (b"x-actor-id", b"a1"),
            (b"x-tenant-id", b"t1"),
            (b"x-role", b"ops"),
            (b"x-correlation-id", b"c1"),
            (b"x-service-identity", b"lotus-gateway"),
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch("src.services.query_service.app.enterprise_readiness.emit_audit_event") as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 200
    assert audit.call_args.kwargs["action"] == "GET /api/v1/portfolios/PB1"
    assert audit.call_args.kwargs["metadata"] == {
        "status_code": 200,
        "access_type": "read",
    }


@pytest.mark.asyncio
async def test_enterprise_middleware_rejects_payload_too_large(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "1")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"2")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_enterprise_middleware_handles_invalid_content_length(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    middleware = build_enterprise_audit_middleware()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integration",
        "headers": [(b"content-length", b"invalid")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    }
    request = Request(scope)

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_enterprise_middleware_omits_not_set_correlation_on_denied_audit(monkeypatch):
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
        with patch("src.services.query_service.app.enterprise_readiness.emit_audit_event") as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 403
    assert audit.call_args.kwargs["correlation_id"] is None


@pytest.mark.asyncio
async def test_enterprise_middleware_omits_not_set_correlation_on_write_audit(monkeypatch):
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
        with patch("src.services.query_service.app.enterprise_readiness.emit_audit_event") as audit:
            response = await middleware(request, _call_next)
    finally:
        correlation_id_var.reset(token)

    assert response.status_code == 200
    assert audit.call_args.kwargs["correlation_id"] is None


def test_emit_audit_event_preserves_none_correlation():
    with patch("src.services.query_service.app.enterprise_readiness.logger.info") as logger_info:
        emit_audit_event(
            action="WRITE /api/v1/portfolios",
            actor_id="actor-1",
            tenant_id="tenant-1",
            role="ops",
            correlation_id=None,
            metadata={"status_code": 202},
        )

    audit_payload = logger_info.call_args.kwargs["extra"]["audit"]
    assert audit_payload["correlation_id"] is None
