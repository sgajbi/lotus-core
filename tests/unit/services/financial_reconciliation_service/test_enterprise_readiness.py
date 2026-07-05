from time import time
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.enterprise_readiness import (
    _enterprise_auth_context_signature,
    _normalize_headers,
)

from src.services.financial_reconciliation_service.app.enterprise_readiness import (
    _required_capability,
    authorize_request,
    authorize_write_request,
    build_enterprise_audit_middleware,
    financial_reconciliation_capability_rules,
    load_capability_rules,
    validate_enterprise_runtime_config,
)
from src.services.financial_reconciliation_service.app.main import app


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


def test_financial_reconciliation_rules_cover_all_control_routes(monkeypatch) -> None:
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)
    rules = load_capability_rules()
    control_routes = {
        f"{method} {route.path}"
        for route in _iter_routes(app.routes)
        for method in getattr(route, "methods", set())
        if getattr(route, "path", "").startswith("/reconciliation/")
        and method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert control_routes <= rules.keys()
    assert control_routes == financial_reconciliation_capability_rules().keys()


def test_financial_reconciliation_write_requires_route_capability(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)

    denied, denied_reason = authorize_write_request(
        "POST",
        "/reconciliation/runs/transaction-cashflow",
        _enterprise_headers("financial_reconciliation.controls.read"),
    )
    assert denied is False
    assert denied_reason == "missing_capability:financial_reconciliation.controls.run"

    allowed, allowed_reason = authorize_write_request(
        "POST",
        "/reconciliation/runs/transaction-cashflow",
        _enterprise_headers("financial_reconciliation.controls.run"),
    )
    assert allowed is True
    assert allowed_reason is None


def test_financial_reconciliation_read_requires_route_capability(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    _configure_auth_context_env(monkeypatch)

    denied, denied_reason = authorize_request(
        "GET",
        "/reconciliation/runs/FRR-001/findings",
        _enterprise_headers("financial_reconciliation.controls.run"),
    )
    assert denied is False
    assert denied_reason == "missing_capability:financial_reconciliation.controls.read"

    allowed, allowed_reason = authorize_request(
        "GET",
        "/reconciliation/runs/FRR-001/findings",
        _enterprise_headers("financial_reconciliation.controls.read"),
    )
    assert allowed is True
    assert allowed_reason is None


def test_financial_reconciliation_exact_route_policy_does_not_authorize_subtrees() -> None:
    assert _required_capability("GET", "/reconciliation/runs/FRR-001/findings/extra") is None
    assert (
        _required_capability("GET", "/reconciliation/runs/FRR-001/findings")
        == "financial_reconciliation.controls.read"
    )


def test_validate_financial_reconciliation_runtime_accepts_default_rules(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    monkeypatch.delenv("ENTERPRISE_CAPABILITY_RULES_JSON", raising=False)

    issues = validate_enterprise_runtime_config()

    assert "missing_capability_rules" not in issues
    assert "missing_primary_key_id" not in issues


@pytest.mark.asyncio
async def test_financial_reconciliation_enterprise_middleware_emits_denied_write_audit(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    middleware = build_enterprise_audit_middleware()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/reconciliation/runs/transaction-cashflow",
            "headers": [(b"content-length", b"0")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    with patch(
        "src.services.financial_reconciliation_service.app.enterprise_readiness.emit_audit_event"
    ) as audit:
        response = await middleware(request, _call_next)

    assert response.status_code == 403
    assert audit.call_args.kwargs["action"] == (
        "DENY POST /reconciliation/runs/transaction-cashflow"
    )
    assert audit.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")
