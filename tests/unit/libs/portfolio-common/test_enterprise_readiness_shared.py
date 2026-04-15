from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import Response

from portfolio_common.enterprise_readiness import (
    EnterpriseReadinessRuntime,
    build_enterprise_audit_middleware,
    redact_sensitive,
)


@dataclass(frozen=True)
class _Settings:
    enterprise_policy_version: str = "policy-v1"
    enterprise_primary_key_id: str = ""
    enterprise_feature_flags: dict[str, object] | None = None
    enterprise_capability_rules: dict[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enterprise_feature_flags",
            self.enterprise_feature_flags or {},
        )
        object.__setattr__(
            self,
            "enterprise_capability_rules",
            self.enterprise_capability_rules or {},
        )


def _runtime(
    *,
    settings: _Settings = _Settings(),
    authz_enabled: bool = False,
    max_payload_bytes: int = 1_048_576,
) -> EnterpriseReadinessRuntime:
    def _env_bool(name: str, default: bool) -> bool:
        if name == "ENTERPRISE_ENFORCE_AUTHZ":
            return authz_enabled
        return default

    def _env_int(name: str, default: int) -> int:
        if name == "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES":
            return max_payload_bytes
        return default

    return EnterpriseReadinessRuntime(
        service_name="lotus-core-test",
        load_settings=lambda: settings,
        env_bool=_env_bool,
        env_int=_env_int,
        logger=Mock(),
    )


def test_authorize_write_request_enforces_capability_rules() -> None:
    runtime = _runtime(
        authz_enabled=True,
        settings=_Settings(
            enterprise_primary_key_id="primary",
            enterprise_capability_rules={"POST /transactions": "transactions.write"},
        ),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": "transactions.read",
    }

    allowed, reason = runtime.authorize_write_request("POST", "/transactions/import", headers)

    assert allowed is False
    assert reason == "missing_capability:transactions.write"


def test_redact_sensitive_masks_nested_values() -> None:
    redacted = redact_sensitive(
        {"authorization": "Bearer token", "nested": [{"account_number": "1234"}]}
    )

    assert redacted == {
        "authorization": "***REDACTED***",
        "nested": [{"account_number": "***REDACTED***"}],
    }


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_uses_injected_audit_emitter_on_denial() -> None:
    runtime = _runtime(authz_enabled=True)
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/integration",
            "headers": [(b"content-length", b"0")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)

    assert response.status_code == 403
    audit_emitter.assert_called_once()
    assert audit_emitter.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_adds_policy_header_and_audits_write() -> None:
    runtime = _runtime(settings=_Settings(enterprise_policy_version="policy-v2"))
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/integration",
            "headers": [
                (b"content-length", b"0"),
                (b"x-actor-id", b"advisor-1"),
                (b"x-tenant-id", b"tenant-1"),
                (b"x-role", b"portfolio_ops"),
                (b"x-correlation-id", b"corr-1"),
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=202)

    response = await middleware(request, _call_next)

    assert response.status_code == 202
    assert response.headers["X-Enterprise-Policy-Version"] == "policy-v2"
    audit_emitter.assert_called_once_with(
        action="POST /api/v1/integration",
        actor_id="advisor-1",
        tenant_id="tenant-1",
        role="portfolio_ops",
        correlation_id="corr-1",
        metadata={"status_code": 202},
    )
