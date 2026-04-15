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
    enterprise_enforce_authz: bool = False
    enterprise_enforce_read_authz: bool = False
    enterprise_audit_reads: bool = False
    enterprise_require_capability_rules: bool = False
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
    read_authz_enabled: bool = False,
    read_audit_enabled: bool = False,
    require_capability_rules: bool = False,
    max_payload_bytes: int = 1_048_576,
) -> EnterpriseReadinessRuntime:
    settings = _Settings(
        enterprise_policy_version=settings.enterprise_policy_version,
        enterprise_primary_key_id=settings.enterprise_primary_key_id,
        enterprise_enforce_authz=authz_enabled or settings.enterprise_enforce_authz,
        enterprise_enforce_read_authz=(
            read_authz_enabled or settings.enterprise_enforce_read_authz
        ),
        enterprise_audit_reads=read_audit_enabled or settings.enterprise_audit_reads,
        enterprise_require_capability_rules=(
            require_capability_rules or settings.enterprise_require_capability_rules
        ),
        enterprise_feature_flags=settings.enterprise_feature_flags,
        enterprise_capability_rules=settings.enterprise_capability_rules,
    )

    def _env_bool(name: str, default: bool) -> bool:
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


def test_runtime_uses_typed_settings_for_enterprise_flags() -> None:
    settings = _Settings(
        enterprise_enforce_authz=True,
        enterprise_enforce_read_authz=True,
        enterprise_audit_reads=True,
        enterprise_require_capability_rules=True,
    )
    runtime = EnterpriseReadinessRuntime(
        service_name="lotus-core-test",
        load_settings=lambda: settings,
        env_bool=lambda _name, _default: False,
        env_int=lambda _name, default: default,
        logger=Mock(),
    )

    assert runtime.env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false") is True
    assert runtime.env_enabled("ENTERPRISE_ENFORCE_READ_AUTHZ", "false") is True
    assert runtime.env_enabled("ENTERPRISE_AUDIT_READS", "false") is True
    assert runtime.env_enabled("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false") is True


def test_feature_flags_fail_closed_for_invalid_shapes() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_feature_flags={
                "not.object": True,
                "tenant.not.object": {"tenant-1": True},
                "global.not.object": {"*": True},
            }
        )
    )

    assert runtime.is_feature_enabled("not.object", "tenant-1", "ops") is False
    assert runtime.is_feature_enabled("tenant.not.object", "tenant-1", "ops") is False
    assert runtime.is_feature_enabled("global.not.object", "tenant-2", "ops") is False


def test_authorize_request_enforces_read_capability_rules_when_enabled() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        settings=_Settings(
            enterprise_primary_key_id="primary",
            enterprise_capability_rules={"GET /portfolios": "portfolios.read"},
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

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_capability:portfolios.read"


def test_authorize_request_allows_read_when_read_authorization_is_disabled() -> None:
    runtime = _runtime(read_authz_enabled=False)

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", {})

    assert allowed is True
    assert reason is None


def test_authorize_request_requires_matching_capability_rule_when_configured() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_Settings(enterprise_primary_key_id="primary"),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": "portfolios.read",
    }

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_capability_rule"


def test_authorize_request_rejects_blank_required_header_values() -> None:
    runtime = _runtime(read_authz_enabled=True)
    headers = {
        "X-Actor-Id": " ",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
    }

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_headers:x-actor-id"


def test_authorize_request_rejects_blank_service_identity() -> None:
    runtime = _runtime(read_authz_enabled=True)
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": " ",
    }

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_service_identity"


def test_required_capability_matches_only_path_segments() -> None:
    runtime = _runtime(
        settings=_Settings(enterprise_capability_rules={"GET /portfolios": "portfolios.read"}),
    )

    assert runtime.required_capability("GET", "/portfolios/P1") == "portfolios.read"
    assert runtime.required_capability("GET", "/portfolios-v2/P1") is None


def test_required_capability_prefers_more_specific_rule() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_capability_rules={
                "GET /portfolios": "portfolios.read",
                "GET /portfolios/P1/analytics": "portfolio.analytics.read",
            }
        ),
    )

    assert (
        runtime.required_capability("GET", "/portfolios/P1/analytics/reference")
        == "portfolio.analytics.read"
    )


def test_capability_rules_keep_only_actionable_method_path_mappings() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_capability_rules={
                "get /portfolios/": " portfolios.read ",
                "GET portfolios": "missing.leading.slash",
                "GET": "missing.path",
                "TRACE /portfolios": "unsupported.method",
                "POST /transactions": "",
                "DELETE /orders": {"not": "a string"},
            }
        )
    )

    assert runtime.load_capability_rules() == {"GET /portfolios": "portfolios.read"}


def test_runtime_config_treats_only_invalid_capability_rules_as_missing() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_Settings(
            enterprise_primary_key_id="primary",
            enterprise_capability_rules={"GET /portfolios": ""},
        ),
    )

    assert "missing_capability_rules" in runtime.validate_enterprise_runtime_config()


def test_validate_enterprise_runtime_config_checks_primary_key_for_read_authorization() -> None:
    runtime = _runtime(read_authz_enabled=True)

    assert "missing_primary_key_id" in runtime.validate_enterprise_runtime_config()


def test_validate_enterprise_runtime_config_reports_missing_capability_rules() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_Settings(enterprise_primary_key_id="primary"),
    )

    assert "missing_capability_rules" in runtime.validate_enterprise_runtime_config()


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


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_does_not_audit_reads_by_default() -> None:
    runtime = _runtime()
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [(b"x-correlation-id", b"corr-read")],
            "query_string": b"tenant_id=tenant-1",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)

    assert response.status_code == 200
    audit_emitter.assert_not_called()


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_audits_reads_when_enabled() -> None:
    runtime = _runtime(read_audit_enabled=True)
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [
                (b"x-actor-id", b"advisor-1"),
                (b"x-tenant-id", b"tenant-1"),
                (b"x-role", b"portfolio_viewer"),
                (b"x-correlation-id", b"corr-read"),
            ],
            "query_string": b"client_email=sensitive@example.com",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        return Response(status_code=200)

    response = await middleware(request, _call_next)

    assert response.status_code == 200
    audit_emitter.assert_called_once_with(
        action="GET /api/v1/portfolios",
        actor_id="advisor-1",
        tenant_id="tenant-1",
        role="portfolio_viewer",
        correlation_id="corr-read",
        metadata={"status_code": 200, "access_type": "read"},
    )


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_denies_read_without_headers_when_enabled() -> None:
    runtime = _runtime(read_authz_enabled=True)
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [],
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
    assert audit_emitter.call_args.kwargs["action"] == "DENY GET /api/v1/portfolios"
    assert audit_emitter.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")
