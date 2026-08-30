from dataclasses import dataclass
from time import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request
from fastapi.responses import Response
from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditIdentityPosture,
    SecurityAuditReason,
)
from portfolio_common.domain.tenant import TenantContext
from portfolio_common.enterprise_readiness import (
    EnterpriseReadinessRuntime,
    _enterprise_auth_context_signature,
    _normalize_headers,
    build_enterprise_audit_middleware,
    create_default_enterprise_readiness_runtime,
    create_runtime_security_audit_store,
    redact_sensitive,
)
from portfolio_common.infrastructure.persistence.security_audit_store import (
    PostgresSecurityAuditStore,
)
from portfolio_common.infrastructure_errors import InfrastructureAuditWriteFailed
from portfolio_common.logging_utils import trace_id_var


@dataclass(frozen=True)
class _Settings:
    enterprise_policy_version: str = "policy-v1"
    enterprise_primary_key_id: str = ""
    enterprise_enforce_authz: bool = False
    enterprise_enforce_read_authz: bool = False
    enterprise_audit_reads: bool = False
    enterprise_require_capability_rules: bool = False
    enterprise_enforce_runtime_config: bool = False
    enterprise_secret_rotation_days: int = 90
    enterprise_max_write_payload_bytes: int = 1_048_576
    enterprise_auth_context_hmac_secret: str = ""
    enterprise_auth_context_max_age_seconds: int = 300
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
        enterprise_enforce_runtime_config=settings.enterprise_enforce_runtime_config,
        enterprise_secret_rotation_days=settings.enterprise_secret_rotation_days,
        enterprise_max_write_payload_bytes=(
            max_payload_bytes
            if max_payload_bytes != 1_048_576
            else settings.enterprise_max_write_payload_bytes
        ),
        enterprise_auth_context_hmac_secret=settings.enterprise_auth_context_hmac_secret,
        enterprise_auth_context_max_age_seconds=settings.enterprise_auth_context_max_age_seconds,
        enterprise_feature_flags=settings.enterprise_feature_flags,
        enterprise_capability_rules=settings.enterprise_capability_rules,
    )

    def _env_bool(name: str, default: bool) -> bool:
        return default

    def _env_int(name: str, default: int) -> int:
        return default

    return EnterpriseReadinessRuntime(
        service_name="lotus-core-test",
        load_settings=lambda: settings,
        env_bool=_env_bool,
        env_int=_env_int,
        logger=Mock(),
    )


def _settings_with_auth_context(**kwargs: object) -> _Settings:
    return _Settings(
        enterprise_primary_key_id="primary",
        enterprise_auth_context_hmac_secret="auth-context-secret",
        **kwargs,
    )


def _signed_enterprise_headers(
    capabilities: str,
    *,
    service_identity: str = "lotus-gateway",
    actor_id: str = "a1",
    tenant_id: str = "t1",
    role: str = "ops",
    correlation_id: str = "c1",
    key_id: str = "primary",
    secret: str = "auth-context-secret",
) -> dict[str, str]:
    headers = {
        "X-Actor-Id": actor_id,
        "X-Tenant-Id": tenant_id,
        "X-Role": role,
        "X-Correlation-Id": correlation_id,
        "X-Service-Identity": service_identity,
        "X-Capabilities": capabilities,
        "X-Enterprise-Auth-Key-Id": key_id,
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }
    headers["X-Enterprise-Auth-Signature"] = _enterprise_auth_context_signature(
        _normalize_headers(headers),
        secret,
    )
    return headers


def test_authorize_write_request_enforces_capability_rules() -> None:
    runtime = _runtime(
        authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"POST /transactions/**": "transactions.write"},
        ),
    )
    headers = _signed_enterprise_headers("transactions.read")

    allowed, reason = runtime.authorize_write_request("POST", "/transactions/import", headers)

    assert allowed is False
    assert reason == "missing_capability:transactions.write"


def test_authorize_capability_fails_closed_until_signed_authority_is_complete() -> None:
    runtime = _runtime(settings=_settings_with_auth_context())
    required_authority = {
        "X-Actor-Id": "support-operator",
        "X-Tenant-Id": "tenant-1",
        "X-Role": "operations",
        "X-Correlation-Id": "correlation-1",
    }

    assert runtime.authorize_capability({}, "core.security_audit.read") == (
        False,
        "missing_headers:x-actor-id,x-correlation-id,x-role,x-tenant-id",
    )
    assert runtime.authorize_capability(
        required_authority,
        "core.security_audit.read",
    ) == (False, "missing_service_identity")
    assert runtime.authorize_capability(
        {**required_authority, "X-Service-Identity": "lotus-gateway"},
        "core.security_audit.read",
    ) == (False, "invalid_auth_context_key_id")
    unsigned_runtime = _runtime()
    assert unsigned_runtime.authorize_capability(
        {**required_authority, "X-Service-Identity": "lotus-gateway"},
        "core.security_audit.read",
    ) == (False, "missing_verified_service_principal")
    invalid_timestamp_headers = _signed_enterprise_headers("core.security_audit.read")
    invalid_timestamp_headers["X-Enterprise-Auth-Timestamp"] = "not-a-timestamp"
    assert runtime.authorize_capability(
        invalid_timestamp_headers,
        "core.security_audit.read",
    ) == (False, "invalid_auth_context_timestamp")
    stale_headers = _signed_enterprise_headers("core.security_audit.read")
    stale_headers["X-Enterprise-Auth-Timestamp"] = "0"
    assert runtime.authorize_capability(
        stale_headers,
        "core.security_audit.read",
    ) == (False, "stale_auth_context")
    assert runtime.authorize_capability(
        _signed_enterprise_headers("core.security_audit.read"),
        "core.security_audit.read",
    ) == (True, None)


def test_runtime_uses_typed_settings_for_enterprise_flags() -> None:
    settings = _Settings(
        enterprise_enforce_authz=True,
        enterprise_enforce_read_authz=True,
        enterprise_audit_reads=True,
        enterprise_require_capability_rules=True,
        enterprise_enforce_runtime_config=True,
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
    assert runtime.env_enabled("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "false") is True


def test_runtime_uses_typed_settings_for_enterprise_integer_knobs() -> None:
    settings = _Settings(
        enterprise_secret_rotation_days=30,
        enterprise_max_write_payload_bytes=2048,
    )
    runtime = EnterpriseReadinessRuntime(
        service_name="lotus-core-test",
        load_settings=lambda: settings,
        env_bool=lambda _name, default: default,
        env_int=lambda _name, _default: 1,
        logger=Mock(),
    )

    assert runtime.env_integer("ENTERPRISE_SECRET_ROTATION_DAYS", 90) == 30
    assert runtime.env_integer("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576) == 2048


def test_default_enterprise_runtime_loads_shared_env_settings(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("ENTERPRISE_POLICY_VERSION", "policy-env")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "primary-key")
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "2048")
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        '{"GET /portfolios/**": "portfolios.read"}',
    )

    runtime = create_default_enterprise_readiness_runtime(
        service_name="test-service",
        logger=Mock(),
    )

    assert runtime.enterprise_policy_version() == "policy-env"
    assert runtime.env_enabled("ENTERPRISE_ENFORCE_READ_AUTHZ", "false") is True
    assert runtime.env_integer("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576) == 2048
    assert runtime.required_capability("GET", "/portfolios/P1") == "portfolios.read"
    assert "missing_primary_key_id" not in runtime.validate_enterprise_runtime_config()


def test_default_enterprise_runtime_uses_production_security_profile(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    monkeypatch.delenv("ENTERPRISE_ENFORCE_AUTHZ", raising=False)
    monkeypatch.delenv("ENTERPRISE_ENFORCE_READ_AUTHZ", raising=False)
    monkeypatch.delenv("ENTERPRISE_AUDIT_READS", raising=False)
    monkeypatch.delenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", raising=False)
    monkeypatch.delenv("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", raising=False)
    monkeypatch.delenv("ENTERPRISE_PRIMARY_KEY_ID", raising=False)

    runtime = create_default_enterprise_readiness_runtime(
        service_name="test-service",
        logger=Mock(),
    )

    assert runtime.env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false") is True
    assert runtime.env_enabled("ENTERPRISE_ENFORCE_READ_AUTHZ", "false") is True
    assert runtime.env_enabled("ENTERPRISE_AUDIT_READS", "false") is True
    assert runtime.env_enabled("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false") is True
    with pytest.raises(RuntimeError, match="missing_primary_key_id"):
        runtime.validate_enterprise_runtime_config()


def test_promoted_profile_cannot_disable_strict_enterprise_validation(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")
    monkeypatch.delenv("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", raising=False)
    runtime = create_default_enterprise_readiness_runtime(
        service_name="test-service",
        logger=Mock(),
    )

    with pytest.raises(RuntimeError, match="missing_policy_version"):
        monkeypatch.setenv("ENTERPRISE_POLICY_VERSION", "")
        runtime.validate_enterprise_runtime_config()


def test_runtime_config_rejects_unbounded_policy_version(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    runtime = _runtime(settings=_Settings(enterprise_policy_version="v" * 65))

    with pytest.raises(RuntimeError, match="policy_version_invalid"):
        runtime.validate_enterprise_runtime_config()


def test_promoted_runtime_rejects_disabled_read_audit(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    runtime = _runtime(settings=_Settings(enterprise_audit_reads=False))

    with pytest.raises(RuntimeError, match="promoted_read_audit_disabled"):
        runtime.validate_enterprise_runtime_config()


def test_unset_environment_allows_schema_tooling_with_forced_runtime_read_audit(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    runtime = _runtime(settings=_Settings(enterprise_audit_reads=False))

    assert runtime.validate_enterprise_runtime_config() == []


def test_security_audit_store_is_log_only_only_for_explicit_local_profiles(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    assert create_runtime_security_audit_store(service_name="query_service") is None

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")
    assert isinstance(
        create_runtime_security_audit_store(service_name="query_service"),
        PostgresSecurityAuditStore,
    )


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
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios/**": "portfolios.read"},
        ),
    )
    headers = _signed_enterprise_headers("transactions.read")

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_capability:portfolios.read"


def test_authorize_request_allows_read_when_read_authorization_is_disabled() -> None:
    runtime = _runtime(read_authz_enabled=False)

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", {})

    assert allowed is True
    assert reason is None


def test_authorize_request_enforces_source_data_post_routes_as_read_contracts() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        settings=_settings_with_auth_context(),
    )
    headers = _signed_enterprise_headers(
        "source_data.portfolio_timeseries_input.read",
        service_identity="lotus-performance",
    )

    allowed, reason = runtime.authorize_request(
        "POST",
        "/integration/portfolios/PB1/analytics/portfolio-timeseries",
        headers,
    )

    assert allowed is True
    assert reason is None


def test_authorize_request_matches_fastapi_path_templates_for_source_data_rules() -> None:
    runtime = _runtime(read_authz_enabled=True, settings=_settings_with_auth_context())
    headers = _signed_enterprise_headers(
        "source_data.reconciliation_evidence_bundle.read",
        service_identity="lotus-manage",
    )

    allowed, reason = runtime.authorize_request(
        "GET",
        "/support/portfolios/PB1/reconciliation-runs/run-1/findings",
        headers,
    )

    assert allowed is True
    assert reason is None


def test_authorize_request_normalizes_method_before_capability_lookup() -> None:
    runtime = _runtime(read_authz_enabled=True, settings=_settings_with_auth_context())
    headers = _signed_enterprise_headers(
        "source_data.reconciliation_evidence_bundle.read",
        service_identity="lotus-manage",
    )

    allowed, reason = runtime.authorize_request(
        " get ",
        "/support/portfolios/PB1/reconciliation-runs/run-1/findings",
        headers,
    )

    assert allowed is True
    assert reason is None


def test_authorize_request_requires_matching_capability_rule_when_configured() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_settings_with_auth_context(),
    )
    headers = _signed_enterprise_headers("portfolios.read")

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
    runtime = _runtime(read_authz_enabled=True, settings=_settings_with_auth_context())
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


def test_authorize_request_rejects_forged_capability_headers_without_signature() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios/**": "portfolios.read"}
        ),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "lotus-gateway",
        "X-Capabilities": "portfolios.read",
        "X-Enterprise-Auth-Key-Id": "primary",
        "X-Enterprise-Auth-Timestamp": str(int(time())),
    }

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "missing_auth_context_signature"


def test_authorize_request_rejects_forged_service_identity_signature() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios/**": "portfolios.read"}
        ),
    )
    headers = _signed_enterprise_headers("portfolios.read")
    headers["X-Service-Identity"] = "forged-service"

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "invalid_auth_context_signature"


def test_authorize_request_rejects_authorization_as_presence_marker() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios/**": "portfolios.read"}
        ),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "Authorization": "Bearer unsigned.jwt.token",
        "X-Capabilities": "portfolios.read",
    }

    allowed, reason = runtime.authorize_request("GET", "/portfolios/P1", headers)

    assert allowed is False
    assert reason == "unverified_authorization_principal"


def test_required_capability_matches_only_path_segments() -> None:
    runtime = _runtime(
        settings=_Settings(enterprise_capability_rules={"GET /portfolios/**": "portfolios.read"}),
    )

    assert runtime.required_capability("GET", "/portfolios/P1") == "portfolios.read"
    assert runtime.required_capability("GET", "/portfolios-v2/P1") is None


def test_required_capability_template_rules_match_exact_segment_count() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_capability_rules={
                "GET /portfolios/{portfolio_id}": "portfolio.summary.read",
            }
        ),
    )

    assert runtime.required_capability("GET", "/portfolios/P1") == "portfolio.summary.read"
    assert runtime.required_capability("GET", "/portfolios/P1/analytics") is None


def test_required_capability_template_subtree_requires_explicit_wildcard() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_capability_rules={
                "GET /portfolios/{portfolio_id}/**": "portfolio.subtree.read",
            }
        ),
    )

    assert runtime.required_capability("GET", "/portfolios/P1") == "portfolio.subtree.read"
    assert (
        runtime.required_capability("GET", "/portfolios/P1/analytics/reference")
        == "portfolio.subtree.read"
    )


def test_required_capability_prefers_more_specific_rule() -> None:
    runtime = _runtime(
        settings=_Settings(
            enterprise_capability_rules={
                "GET /portfolios/**": "portfolios.read",
                "GET /portfolios/P1/analytics/**": "portfolio.analytics.read",
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
                "get /portfolios/**": " portfolios.read ",
                "GET portfolios": "missing.leading.slash",
                "GET": "missing.path",
                "TRACE /portfolios": "unsupported.method",
                "POST /transactions": "",
                "DELETE /orders": {"not": "a string"},
                "GET /oversized-capability": "c" * 129,
                f"GET /{'p' * 257}": "oversized.path",
            }
        )
    )

    assert runtime.load_capability_rules()["GET /portfolios/**"] == "portfolios.read"
    assert "GET /oversized-capability" not in runtime.load_capability_rules()
    assert (
        runtime.load_capability_rules()[
            "POST /integration/portfolios/{portfolio_id}/analytics/reference"
        ]
        == "source_data.portfolio_analytics_reference.read"
    )


def test_runtime_config_uses_source_data_default_capability_rules() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios": ""},
        ),
    )

    assert "missing_capability_rules" not in runtime.validate_enterprise_runtime_config()


def test_validate_enterprise_runtime_config_rejects_nonpositive_payload_limit() -> None:
    runtime = _runtime(max_payload_bytes=0)

    assert "max_write_payload_bytes_out_of_range" in runtime.validate_enterprise_runtime_config()


def test_validate_enterprise_runtime_config_checks_primary_key_for_read_authorization() -> None:
    runtime = _runtime(read_authz_enabled=True)

    assert "missing_primary_key_id" in runtime.validate_enterprise_runtime_config()


def test_validate_enterprise_runtime_config_accepts_source_data_default_rules() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_settings_with_auth_context(),
    )

    assert "missing_capability_rules" not in runtime.validate_enterprise_runtime_config()


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

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.body == (
        b'{"type":"https://lotus.local/problems/enterprise/tenant-context-required",'
        b'"title":"Tenant Context Required","status":401,'
        b'"detail":"A nonblank X-Tenant-Id header is required for this route.",'
        b'"instance":"/api/v1/integration","error_code":"TENANT_CONTEXT_REQUIRED",'
        b'"correlation_id":""}'
    )
    audit_emitter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_header", [b"", b"   "])
async def test_shared_enterprise_middleware_rejects_missing_or_blank_tenant_before_route(
    tenant_header: bytes,
) -> None:
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
    )
    headers = [] if not tenant_header else [(b"x-tenant-id", tenant_header)]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    response = await middleware(request, call_next)

    assert response.status_code == 401
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_allows_operational_paths_without_headers() -> None:
    runtime = _runtime(read_authz_enabled=True, require_capability_rules=True)
    audit_emitter = Mock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health/live",
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

    assert response.status_code == 200
    assert response.headers["X-Enterprise-Policy-Version"] == "policy-v1"
    audit_emitter.assert_not_called()


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_normalizes_audit_identity_values() -> None:
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
            "headers": [
                (b"x-actor-id", b"  "),
                (b"x-tenant-id", b" tenant-1 "),
                (b"x-role", b" ops "),
                (b"x-correlation-id", b"corr-1"),
                (b"x-service-identity", b"lotus-gateway"),
            ],
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
    assert audit_emitter.call_args.kwargs["actor_id"] == "unknown"
    assert audit_emitter.call_args.kwargs["tenant_id"] == "tenant-1"
    assert audit_emitter.call_args.kwargs["role"] == "ops"


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
        action="POST /unclassified",
        actor_id="advisor-1",
        tenant_id="tenant-1",
        role="portfolio_ops",
        correlation_id="corr-1",
        metadata={"status_code": 202},
    )


@pytest.mark.asyncio
async def test_explicit_local_enterprise_middleware_does_not_audit_reads_by_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    runtime = _runtime()
    audit_emitter = Mock()
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=audit_emitter,
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [
                (b"x-correlation-id", b"corr-read"),
                (b"x-tenant-id", b"tenant-1"),
            ],
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
    store.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_unset_environment_forces_durable_read_audit(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(settings=_Settings(enterprise_audit_reads=False)),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [(b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    response = await middleware(
        request,
        AsyncMock(return_value=Response(status_code=200)),
    )

    assert response.status_code == 200
    store.append.assert_awaited_once()


@pytest.mark.asyncio
async def test_promoted_middleware_forces_durable_read_audit_when_flag_is_false(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(settings=_Settings(enterprise_audit_reads=False)),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/portfolios",
            "headers": [(b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    response = await middleware(
        request,
        AsyncMock(return_value=Response(status_code=200)),
    )

    assert response.status_code == 200
    event = store.append.await_args.args[0]
    assert event.method.value == "GET"
    assert event.decision is SecurityAuditDecision.ALLOW


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
        action="GET /unclassified",
        actor_id="advisor-1",
        tenant_id="tenant-1",
        role="portfolio_viewer",
        correlation_id="corr-read",
        metadata={"status_code": 200, "access_type": "read"},
    )


@pytest.mark.asyncio
async def test_shared_enterprise_middleware_denies_read_with_only_tenant_when_authz_enabled() -> (
    None
):
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
            "headers": [(b"x-tenant-id", b"tenant-1")],
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
    assert audit_emitter.call_args.kwargs["action"] == "DENY GET /unclassified"
    assert audit_emitter.call_args.kwargs["metadata"]["reason"].startswith("missing_headers:")


@pytest.mark.asyncio
async def test_durable_allow_is_written_before_protected_route_with_verified_identity() -> None:
    runtime = _runtime(
        authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"POST /portfolios/{portfolio_id}": "portfolio.write"}
        ),
    )
    store = Mock()
    ordering: list[str] = []

    async def _append(event) -> None:
        ordering.append("audit")
        store.event = event

    store.append = AsyncMock(side_effect=_append)
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    headers = _signed_enterprise_headers("portfolio.write")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/portfolios/PB-001",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "query_string": b"client_email=sensitive@example.com",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    async def _call_next(_: Request) -> Response:
        assert request.state.enterprise_verified_tenant_id == "t1"
        tenant_context = request.state.tenant_context
        assert isinstance(tenant_context, TenantContext)
        assert tenant_context.tenant_id_text == "t1"
        assert tenant_context.identity_verified is True
        ordering.append("route")
        return Response(status_code=200)

    with patch(
        "portfolio_common.enterprise_readiness.observe_security_audit_delivery"
    ) as delivery_metric:
        response = await middleware(request, _call_next)

    assert response.status_code == 200
    assert ordering == ["audit", "route"]
    event = store.event
    assert event.component is SecurityAuditComponent.QUERY
    assert event.route_template == "/portfolios/{portfolio_id}"
    assert event.decision is SecurityAuditDecision.ALLOW
    assert event.reason is SecurityAuditReason.AUTHORIZED
    assert event.required_capability == "portfolio.write"
    assert event.identity_posture is SecurityAuditIdentityPosture.VERIFIED
    assert (event.service_identity, event.actor_id, event.tenant_id, event.role) == (
        "lotus-gateway",
        "a1",
        "t1",
        "ops",
    )
    assert "PB-001" not in repr(event)
    assert "sensitive@example.com" not in repr(event)
    delivery_metric.assert_called_once_with(service="query_service", outcome="delivered")


@pytest.mark.asyncio
async def test_durable_denial_does_not_fabricate_unverified_identity() -> None:
    runtime = _runtime(
        read_authz_enabled=True,
        require_capability_rules=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"GET /portfolios/{portfolio_id}": "portfolio.read"}
        ),
    )
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/portfolios/PB-SECRET",
            "headers": [
                (b"x-actor-id", b"unverified-advisor"),
                (b"x-tenant-id", b"tenant-1"),
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    response = await middleware(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()
    event = store.append.await_args.args[0]
    assert event.route_template == "/portfolios/{portfolio_id}"
    assert event.decision is SecurityAuditDecision.DENY
    assert event.reason is SecurityAuditReason.AUTHORIZATION_POLICY_DENIED
    assert event.identity_posture is SecurityAuditIdentityPosture.UNVERIFIED
    assert (event.service_identity, event.actor_id, event.tenant_id, event.role) == (
        None,
        None,
        None,
        None,
    )
    assert "PB-SECRET" not in repr(event)
    assert "unverified-advisor" not in repr(event)


@pytest.mark.asyncio
async def test_oversized_signed_lineage_is_denied_and_recorded_without_raw_values() -> None:
    runtime = _runtime(
        authz_enabled=True,
        settings=_settings_with_auth_context(
            enterprise_capability_rules={"POST /portfolios/{portfolio_id}": "portfolio.write"}
        ),
    )
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    oversized_correlation = "c" * 129
    headers = _signed_enterprise_headers("portfolio.write", correlation_id=oversized_correlation)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/portfolios/PB-001",
            "headers": [
                *[(key.lower().encode(), value.encode()) for key, value in headers.items()],
                (b"x-trace-id", b"not-a-w3c-trace-id"),
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    response = await middleware(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()
    event = store.append.await_args.args[0]
    assert event.identity_posture is SecurityAuditIdentityPosture.UNVERIFIED
    assert event.correlation_id is None
    assert event.trace_id is None
    assert oversized_correlation not in repr(event)


@pytest.mark.asyncio
async def test_durable_event_preserves_canonical_runtime_trace_context() -> None:
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/portfolios/PB-001",
            "headers": [(b"content-length", b"0"), (b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    runtime_trace_id = "0123456789abcdef0123456789abcdef"
    trace_token = trace_id_var.set(runtime_trace_id)
    try:
        response = await middleware(
            request,
            AsyncMock(return_value=Response(status_code=200)),
        )
    finally:
        trace_id_var.reset(trace_token)

    assert response.status_code == 200
    assert store.append.await_args.args[0].trace_id == runtime_trace_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trace_headers", "expected_trace_id"),
    [
        (
            [
                (
                    b"traceparent",
                    b"00-11111111111111111111111111111111-2222222222222222-01",
                ),
                (b"x-trace-id", b"33333333333333333333333333333333"),
            ],
            "11111111111111111111111111111111",
        ),
        (
            [(b"x-trace-id", b"33333333333333333333333333333333")],
            "33333333333333333333333333333333",
        ),
    ],
)
async def test_durable_event_uses_governed_trace_source_precedence(
    trace_headers: list[tuple[bytes, bytes]],
    expected_trace_id: str,
) -> None:
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/portfolios/PB-001",
            "headers": [
                (b"content-length", b"0"),
                (b"x-tenant-id", b"tenant-1"),
                *trace_headers,
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    context_token = trace_id_var.set("44444444444444444444444444444444")
    try:
        response = await middleware(
            request,
            AsyncMock(return_value=Response(status_code=200)),
        )
    finally:
        trace_id_var.reset(context_token)

    assert response.status_code == 200
    assert store.append.await_args.args[0].trace_id == expected_trace_id


@pytest.mark.asyncio
async def test_payload_denial_stops_when_durable_audit_is_unavailable() -> None:
    store = Mock()
    store.append = AsyncMock(side_effect=InfrastructureAuditWriteFailed())
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(max_payload_bytes=1),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.INGESTION,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/transactions",
            "headers": [(b"content-length", b"2")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=201))

    response = await middleware(request, call_next)

    assert response.status_code == 503
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorization_denial_stops_when_durable_audit_is_unavailable() -> None:
    store = Mock()
    store.append = AsyncMock(side_effect=InfrastructureAuditWriteFailed())
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(authz_enabled=True),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.QUERY,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/portfolios/PB-001",
            "headers": [(b"content-length", b"0"), (b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    response = await middleware(request, call_next)

    assert response.status_code == 503
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_audit_failure_returns_safe_503_before_route_execution() -> None:
    store = Mock()
    store.append = AsyncMock(side_effect=InfrastructureAuditWriteFailed())
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.INGESTION,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/transactions/secret-id",
            "headers": [(b"content-length", b"0"), (b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=201))

    with patch(
        "portfolio_common.enterprise_readiness.observe_security_audit_delivery"
    ) as delivery_metric:
        response = await middleware(request, call_next)

    assert response.status_code == 503
    assert response.body == b'{"detail":"security_audit_unavailable"}'
    call_next.assert_not_awaited()
    delivery_metric.assert_called_once_with(service="ingestion_service", outcome="failed")


@pytest.mark.asyncio
async def test_production_profile_override_cannot_disable_fail_closed_audit(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")
    store = Mock()
    store.append = AsyncMock(side_effect=InfrastructureAuditWriteFailed())
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.INGESTION,
        audit_store=store,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/transactions",
            "headers": [(b"content-length", b"0")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=201))

    response = await middleware(request, call_next)

    assert response.status_code == 503
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_audit_failure_can_continue_without_fabricating_evidence() -> None:
    store = Mock()
    store.append = AsyncMock(side_effect=InfrastructureAuditWriteFailed())
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.INGESTION,
        audit_store=store,
        audit_failure_is_fatal=False,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/transactions/secret-id",
            "headers": [(b"content-length", b"0"), (b"x-tenant-id", b"tenant-1")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=201))

    response = await middleware(request, call_next)

    assert response.status_code == 201
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_payload_limit_denial_is_durable_before_rejection() -> None:
    store = Mock()
    store.append = AsyncMock()
    middleware = build_enterprise_audit_middleware(
        runtime=_runtime(max_payload_bytes=10),
        audit_emitter=Mock(),
        component=SecurityAuditComponent.INGESTION,
        audit_store=store,
        audit_failure_is_fatal=True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest/transactions",
            "headers": [(b"content-length", b"11")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=201))

    response = await middleware(request, call_next)

    assert response.status_code == 413
    call_next.assert_not_awaited()
    event = store.append.await_args.args[0]
    assert event.decision is SecurityAuditDecision.DENY
    assert event.reason is SecurityAuditReason.PAYLOAD_TOO_LARGE
