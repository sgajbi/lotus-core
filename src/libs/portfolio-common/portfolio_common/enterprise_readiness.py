"""Shared enterprise readiness policy, authorization, and audit helpers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol, cast
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from portfolio_common.domain.security_audit import (
    SecurityAuditComponent,
    SecurityAuditDecision,
    SecurityAuditEvent,
    SecurityAuditIdentityPosture,
    SecurityAuditMethod,
    SecurityAuditReason,
)
from portfolio_common.enterprise_request_context import (
    audit_authority_headers_are_bounded,
    request_correlation_id,
    request_header_value,
    request_trace_id,
)
from portfolio_common.enterprise_tenant_admission import (
    TenantContextAdmissionError,
    resolve_enterprise_tenant_context,
    tenant_context_required_problem,
)
from portfolio_common.infrastructure.persistence.security_audit_store import (
    PostgresSecurityAuditStore,
)
from portfolio_common.infrastructure_errors import InfrastructureAuditWriteFailed
from portfolio_common.logging_utils import redact_sensitive
from portfolio_common.monitoring import observe_security_audit_delivery
from portfolio_common.ports.security_audit import SecurityAuditStore
from portfolio_common.runtime_settings import (
    LOCAL_CONFIG_ENVIRONMENTS,
    env_bool,
    env_int,
    env_json_map,
    env_str,
    explicit_local_config_profile_enabled,
    production_security_profile_enabled,
    runtime_environment_name,
)
from portfolio_common.source_data_security import source_data_capability_rules

MiddlewareNext = Callable[[Request], Awaitable[Response]]
MiddlewareCallable = Callable[[Request, MiddlewareNext], Awaitable[Response]]
AuditEmitter = Callable[..., None]
MaxWritePayloadBytesResolver = Callable[[Request, int], int]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_AUDIT_METHODS = {"GET", "HEAD"}
READ_AUTHZ_METHODS = {"GET", "HEAD"}
CAPABILITY_RULE_METHODS = WRITE_METHODS | READ_AUTHZ_METHODS
REQUIRED_HEADERS = {"x-actor-id", "x-tenant-id", "x-role", "x-correlation-id"}
CAPABILITY_SUBTREE_WILDCARD = "/**"
ENTERPRISE_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/docs",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/openapi.json",
        "/redoc",
        "/version",
    }
)


class EnterpriseSettings(Protocol):
    @property
    def enterprise_policy_version(self) -> str: ...

    @property
    def enterprise_primary_key_id(self) -> str: ...

    @property
    def enterprise_enforce_authz(self) -> bool: ...

    @property
    def enterprise_enforce_read_authz(self) -> bool: ...

    @property
    def enterprise_audit_reads(self) -> bool: ...

    @property
    def enterprise_require_capability_rules(self) -> bool: ...

    @property
    def enterprise_enforce_runtime_config(self) -> bool: ...

    @property
    def enterprise_secret_rotation_days(self) -> int: ...

    @property
    def enterprise_max_write_payload_bytes(self) -> int: ...

    @property
    def enterprise_auth_context_hmac_secret(self) -> str: ...

    @property
    def enterprise_auth_context_max_age_seconds(self) -> int: ...

    @property
    def enterprise_feature_flags(self) -> dict[str, Any]: ...

    @property
    def enterprise_capability_rules(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DefaultEnterpriseSettings:
    enterprise_policy_version: str
    enterprise_primary_key_id: str
    enterprise_enforce_authz: bool
    enterprise_enforce_read_authz: bool
    enterprise_audit_reads: bool
    enterprise_require_capability_rules: bool
    enterprise_enforce_runtime_config: bool
    enterprise_secret_rotation_days: int
    enterprise_max_write_payload_bytes: int
    enterprise_auth_context_hmac_secret: str
    enterprise_auth_context_max_age_seconds: int
    enterprise_feature_flags: dict[str, Any]
    enterprise_capability_rules: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedServicePrincipal:
    service_identity: str
    capabilities: set[str]


@dataclass(frozen=True, slots=True)
class EnterpriseAuthorizationDecision:
    authorized: bool
    reason: str | None
    required_capability: str | None
    route_template: str
    principal: VerifiedServicePrincipal | None


@dataclass(frozen=True)
class EnterpriseReadinessRuntime:
    service_name: str
    load_settings: Callable[[], EnterpriseSettings]
    env_bool: Callable[[str, bool], bool]
    env_int: Callable[[str, int], int]
    logger: logging.Logger
    default_capability_rules: Callable[[], dict[str, str]] = field(default=lambda: {})

    def env_enabled(self, name: str, default: str = "true") -> bool:
        settings_attr = {
            "ENTERPRISE_ENFORCE_AUTHZ": "enterprise_enforce_authz",
            "ENTERPRISE_ENFORCE_READ_AUTHZ": "enterprise_enforce_read_authz",
            "ENTERPRISE_AUDIT_READS": "enterprise_audit_reads",
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES": "enterprise_require_capability_rules",
            "ENTERPRISE_ENFORCE_RUNTIME_CONFIG": "enterprise_enforce_runtime_config",
        }.get(name)
        if settings_attr:
            return bool(getattr(self.load_settings(), settings_attr))
        return self.env_bool(name, default.strip().lower() in {"1", "true", "yes", "on"})

    def env_integer(self, name: str, default: int) -> int:
        settings = self.load_settings()
        if name == "ENTERPRISE_SECRET_ROTATION_DAYS":
            return int(settings.enterprise_secret_rotation_days)
        if name == "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES":
            return int(settings.enterprise_max_write_payload_bytes)
        return self.env_int(name, default)

    def load_json_map(self, name: str) -> dict[str, Any]:
        settings = self.load_settings()
        if name == "ENTERPRISE_FEATURE_FLAGS_JSON":
            parsed = settings.enterprise_feature_flags
            return parsed if isinstance(parsed, dict) else {}
        if name == "ENTERPRISE_CAPABILITY_RULES_JSON":
            parsed = settings.enterprise_capability_rules
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def enterprise_policy_version(self) -> str:
        return self.load_settings().enterprise_policy_version

    def validate_enterprise_runtime_config(self) -> list[str]:
        issues: list[str] = []
        policy_version = self.enterprise_policy_version()
        _append_issue_if(
            issues,
            "missing_policy_version",
            not policy_version.strip(),
        )
        _append_issue_if(
            issues,
            "policy_version_invalid",
            bool(policy_version.strip())
            and (policy_version != policy_version.strip() or len(policy_version) > 64),
        )
        _append_issue_if(
            issues,
            "secret_rotation_days_out_of_range",
            not _valid_secret_rotation_days(
                self.env_integer("ENTERPRISE_SECRET_ROTATION_DAYS", 90)
            ),
        )
        _append_issue_if(
            issues,
            "max_write_payload_bytes_out_of_range",
            self.env_integer("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576) <= 0,
        )
        authz_enabled = self._authz_enforcement_enabled()
        _append_issue_if(
            issues,
            "promoted_read_audit_disabled",
            runtime_environment_name() not in LOCAL_CONFIG_ENVIRONMENTS
            and not self.env_enabled("ENTERPRISE_AUDIT_READS", "false"),
        )
        _append_issue_if(
            issues,
            "missing_primary_key_id",
            authz_enabled and not self.load_settings().enterprise_primary_key_id.strip(),
        )
        _append_issue_if(
            issues,
            "missing_auth_context_secret",
            authz_enabled and not self.load_settings().enterprise_auth_context_hmac_secret.strip(),
        )
        _append_issue_if(
            issues,
            "missing_capability_rules",
            self._requires_capability_rules(authz_enabled) and not self.load_capability_rules(),
        )

        if issues and (
            self.env_enabled("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "false")
            or not explicit_local_config_profile_enabled()
        ):
            raise RuntimeError(f"enterprise_runtime_config_invalid:{','.join(issues)}")
        return issues

    def _authz_enforcement_enabled(self) -> bool:
        return self.env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false") or self.env_enabled(
            "ENTERPRISE_ENFORCE_READ_AUTHZ", "false"
        )

    def _requires_capability_rules(self, authz_enabled: bool) -> bool:
        return self.env_enabled("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false") and authz_enabled

    def load_feature_flags(self) -> dict[str, dict[str, dict[str, bool]]]:
        return self.load_json_map("ENTERPRISE_FEATURE_FLAGS_JSON")

    def load_capability_rules(self) -> dict[str, str]:
        rules = {
            **source_data_capability_rules(),
            **self.default_capability_rules(),
            **self.load_json_map("ENTERPRISE_CAPABILITY_RULES_JSON"),
        }
        normalized: dict[str, str] = {}
        for key, capability in rules.items():
            normalized_rule = _normalize_capability_rule(key, capability)
            if normalized_rule is None:
                continue
            rule_key, rule_capability = normalized_rule
            normalized[rule_key] = rule_capability
        return normalized

    def is_feature_enabled(self, feature_key: str, tenant_id: str, role: str) -> bool:
        flags = self.load_feature_flags()
        feature = _dict_value(flags, feature_key)
        tenant = _dict_value(feature, tenant_id)
        tenant_override = _feature_flag_value(tenant, role)
        if tenant_override is not None:
            return tenant_override
        global_entry = _dict_value(feature, "*")
        global_default = global_entry.get("*")
        return bool(global_default) if isinstance(global_default, bool) else False

    def authorize_write_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> tuple[bool, str | None]:
        return self.authorize_request(method, path, headers)

    def authorize_capability(
        self,
        headers: dict[str, str],
        required_capability: str,
    ) -> tuple[bool, str | None]:
        normalized_headers = _normalize_headers(headers)
        missing_headers = _missing_required_headers(normalized_headers)
        if missing_headers:
            return False, f"missing_headers:{','.join(missing_headers)}"

        if not _has_service_identity(normalized_headers):
            return False, "missing_service_identity"

        verified_principal = _verified_service_principal(normalized_headers, self.load_settings())
        if isinstance(verified_principal, str):
            return False, verified_principal

        return self._authorize_required_capability(required_capability, verified_principal)

    def authorize_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> tuple[bool, str | None]:
        decision = self.evaluate_request(method, path, headers)
        return decision.authorized, decision.reason

    def evaluate_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> EnterpriseAuthorizationDecision:
        normalized_method = method.strip().upper()
        matched_rule = self.matched_capability_rule(normalized_method, path)
        route_template = matched_rule[0] if matched_rule is not None else "/unclassified"
        required_capability = matched_rule[1] if matched_rule is not None else None
        if not self._request_requires_authorization(normalized_method, required_capability):
            return EnterpriseAuthorizationDecision(
                authorized=True,
                reason=None,
                required_capability=required_capability,
                route_template=route_template,
                principal=None,
            )

        normalized_headers = _normalize_headers(headers)
        missing_headers = _missing_required_headers(normalized_headers)
        if missing_headers:
            return EnterpriseAuthorizationDecision(
                authorized=False,
                reason=f"missing_headers:{','.join(missing_headers)}",
                required_capability=required_capability,
                route_template=route_template,
                principal=None,
            )

        if not _has_service_identity(normalized_headers):
            return EnterpriseAuthorizationDecision(
                authorized=False,
                reason="missing_service_identity",
                required_capability=required_capability,
                route_template=route_template,
                principal=None,
            )

        verified_principal = _verified_service_principal(normalized_headers, self.load_settings())
        if isinstance(verified_principal, str):
            return EnterpriseAuthorizationDecision(
                authorized=False,
                reason=verified_principal,
                required_capability=required_capability,
                route_template=route_template,
                principal=None,
            )

        authorized, reason = self._authorize_required_capability(
            required_capability, verified_principal
        )
        return EnterpriseAuthorizationDecision(
            authorized=authorized,
            reason=reason,
            required_capability=required_capability,
            route_template=route_template,
            principal=verified_principal,
        )

    def _request_requires_authorization(
        self,
        normalized_method: str,
        required_capability: str | None,
    ) -> bool:
        requires_write_authz = normalized_method in WRITE_METHODS and self.env_enabled(
            "ENTERPRISE_ENFORCE_AUTHZ",
            "false",
        )
        requires_read_authz = (
            normalized_method in READ_AUTHZ_METHODS or required_capability is not None
        ) and self.env_enabled(
            "ENTERPRISE_ENFORCE_READ_AUTHZ",
            "false",
        )
        return requires_write_authz or requires_read_authz

    def _authorize_required_capability(
        self,
        required_capability: str | None,
        verified_principal: VerifiedServicePrincipal,
    ) -> tuple[bool, str | None]:
        if not required_capability and self.env_enabled(
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false"
        ):
            return False, "missing_capability_rule"
        if required_capability:
            if required_capability not in verified_principal.capabilities:
                return False, f"missing_capability:{required_capability}"

        return True, None

    def required_capability(self, method: str, path: str) -> str | None:
        matched_rule = self.matched_capability_rule(method, path)
        return matched_rule[1] if matched_rule is not None else None

    def matched_capability_rule(self, method: str, path: str) -> tuple[str, str] | None:
        method = method.strip().upper()
        for key, capability in _rules_by_specificity(self.load_capability_rules()):
            prefix = f"{method} "
            if key.upper().startswith(prefix) and _path_matches_rule(path, key[len(prefix) :]):
                return key[len(prefix) :], capability
        return None

    def emit_audit_event(
        self,
        *,
        action: str,
        actor_id: str,
        tenant_id: str,
        role: str,
        correlation_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        self.logger.info(
            "enterprise_audit_event",
            extra={
                "audit": {
                    "service": self.service_name,
                    "action": action,
                    "actor_id": actor_id,
                    "tenant_id": tenant_id,
                    "role": role,
                    "correlation_id": correlation_id,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "policy_version": self.enterprise_policy_version(),
                    "metadata": redact_sensitive(metadata),
                }
            },
        )


def load_default_enterprise_settings(*, service_name: str) -> DefaultEnterpriseSettings:
    production_security_profile = production_security_profile_enabled(service_name=service_name)
    return DefaultEnterpriseSettings(
        enterprise_policy_version=env_str("ENTERPRISE_POLICY_VERSION", "1.0.0"),
        enterprise_primary_key_id=env_str("ENTERPRISE_PRIMARY_KEY_ID", ""),
        enterprise_enforce_authz=env_bool(
            "ENTERPRISE_ENFORCE_AUTHZ",
            production_security_profile,
            service_name=service_name,
        ),
        enterprise_enforce_read_authz=env_bool(
            "ENTERPRISE_ENFORCE_READ_AUTHZ",
            production_security_profile,
            service_name=service_name,
        ),
        enterprise_audit_reads=env_bool(
            "ENTERPRISE_AUDIT_READS",
            production_security_profile,
            service_name=service_name,
        ),
        enterprise_require_capability_rules=env_bool(
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES",
            production_security_profile,
            service_name=service_name,
        ),
        enterprise_enforce_runtime_config=env_bool(
            "ENTERPRISE_ENFORCE_RUNTIME_CONFIG",
            production_security_profile,
            service_name=service_name,
        ),
        enterprise_secret_rotation_days=env_int(
            "ENTERPRISE_SECRET_ROTATION_DAYS",
            90,
            service_name=service_name,
            minimum=1,
        ),
        enterprise_max_write_payload_bytes=env_int(
            "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES",
            1_048_576,
            service_name=service_name,
            minimum=1,
        ),
        enterprise_auth_context_hmac_secret=env_str("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", ""),
        enterprise_auth_context_max_age_seconds=env_int(
            "ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS",
            300,
            service_name=service_name,
            minimum=1,
        ),
        enterprise_feature_flags=env_json_map(
            "ENTERPRISE_FEATURE_FLAGS_JSON",
            service_name=service_name,
        ),
        enterprise_capability_rules=env_json_map(
            "ENTERPRISE_CAPABILITY_RULES_JSON",
            service_name=service_name,
        ),
    )


def create_default_enterprise_readiness_runtime(
    *,
    service_name: str,
    logger: logging.Logger,
) -> EnterpriseReadinessRuntime:
    return EnterpriseReadinessRuntime(
        service_name=service_name,
        load_settings=lambda: cast(
            EnterpriseSettings,
            load_default_enterprise_settings(service_name=service_name),
        ),
        env_bool=lambda name, default: env_bool(name, default, service_name=service_name),
        env_int=lambda name, default: env_int(name, default, service_name=service_name),
        logger=logger,
    )


def validate_default_enterprise_runtime_config(
    *,
    service_name: str,
    logger: logging.Logger,
) -> list[str]:
    runtime = create_default_enterprise_readiness_runtime(
        service_name=service_name,
        logger=logger,
    )
    return runtime.validate_enterprise_runtime_config()


def build_default_enterprise_audit_middleware(
    *,
    service_name: str,
    logger: logging.Logger,
    max_write_payload_bytes_resolver: MaxWritePayloadBytesResolver | None = None,
) -> MiddlewareCallable:
    runtime = create_default_enterprise_readiness_runtime(
        service_name=service_name,
        logger=logger,
    )
    return build_enterprise_audit_middleware(
        runtime=runtime,
        audit_emitter=runtime.emit_audit_event,
        component=SecurityAuditComponent(service_name),
        audit_store=create_runtime_security_audit_store(service_name=service_name),
        max_write_payload_bytes_resolver=max_write_payload_bytes_resolver,
    )


def create_runtime_security_audit_store(*, service_name: str) -> SecurityAuditStore | None:
    """Use durable evidence in promoted profiles and explicit log-only local profiles."""

    _ = service_name
    if explicit_local_config_profile_enabled():
        return None
    return PostgresSecurityAuditStore()


def _dict_value(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key, {})
    return item if isinstance(item, dict) else {}


def _feature_flag_value(tenant_flags: dict[str, Any], role: str) -> bool | None:
    role_value = tenant_flags.get(role)
    if isinstance(role_value, bool):
        return role_value
    wildcard_value = tenant_flags.get("*")
    return wildcard_value if isinstance(wildcard_value, bool) else None


def _append_issue_if(issues: list[str], issue: str, condition: bool) -> None:
    if condition:
        issues.append(issue)


def _valid_secret_rotation_days(rotation_days: int) -> bool:
    return 0 < rotation_days <= 90


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value).strip() for key, value in headers.items()}


def _missing_required_headers(normalized_headers: dict[str, str]) -> list[str]:
    return sorted(header for header in REQUIRED_HEADERS if not normalized_headers.get(header))


def _has_service_identity(normalized_headers: dict[str, str]) -> bool:
    return bool(
        normalized_headers.get("x-service-identity") or normalized_headers.get("authorization")
    )


def _capabilities_from_headers(normalized_headers: dict[str, str]) -> set[str]:
    return {
        part.strip()
        for part in normalized_headers.get("x-capabilities", "").split(",")
        if part.strip()
    }


def _verified_service_principal(
    normalized_headers: dict[str, str],
    settings: EnterpriseSettings,
) -> VerifiedServicePrincipal | str:
    if normalized_headers.get("authorization"):
        return _unsupported_authorization_reason(normalized_headers["authorization"])

    service_identity = normalized_headers.get("x-service-identity", "").strip()
    if not service_identity:
        return "missing_service_identity"
    if not audit_authority_headers_are_bounded(normalized_headers):
        return "invalid_auth_context_field"

    secret = settings.enterprise_auth_context_hmac_secret.strip()
    if not secret:
        return "missing_verified_service_principal"

    key_id = normalized_headers.get("x-enterprise-auth-key-id", "").strip()
    if settings.enterprise_primary_key_id.strip() and key_id != settings.enterprise_primary_key_id:
        return "invalid_auth_context_key_id"

    timestamp = _auth_context_timestamp(normalized_headers)
    if timestamp is None:
        return "invalid_auth_context_timestamp"
    if abs(int(time.time()) - timestamp) > settings.enterprise_auth_context_max_age_seconds:
        return "stale_auth_context"

    signature = normalized_headers.get("x-enterprise-auth-signature", "").strip()
    if not signature:
        return "missing_auth_context_signature"
    expected = _enterprise_auth_context_signature(normalized_headers, secret)
    if not hmac.compare_digest(expected, signature):
        return "invalid_auth_context_signature"

    return VerifiedServicePrincipal(
        service_identity=service_identity,
        capabilities=_capabilities_from_headers(normalized_headers),
    )


def _unsupported_authorization_reason(authorization: str) -> str:
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return "invalid_authorization_header"
    return "unverified_authorization_principal"


def _auth_context_timestamp(normalized_headers: dict[str, str]) -> int | None:
    raw = normalized_headers.get("x-enterprise-auth-timestamp", "")
    try:
        return int(raw)
    except ValueError:
        return None


def _enterprise_auth_context_signature(
    normalized_headers: dict[str, str],
    secret: str,
) -> str:
    canonical = "\n".join(
        (
            "lotus-enterprise-auth-context-v1",
            normalized_headers.get("x-enterprise-auth-key-id", ""),
            normalized_headers.get("x-service-identity", ""),
            normalized_headers.get("x-actor-id", ""),
            normalized_headers.get("x-tenant-id", ""),
            normalized_headers.get("x-role", ""),
            normalized_headers.get("x-correlation-id", ""),
            normalized_headers.get("x-enterprise-auth-timestamp", ""),
            ",".join(sorted(_capabilities_from_headers(normalized_headers))),
        )
    )
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _path_matches_rule(path: str, rule_path: str) -> bool:
    normalized_rule = rule_path.rstrip("/")
    if not normalized_rule or normalized_rule == "/":
        return _normalize_path(path) == "/"
    if normalized_rule.endswith(CAPABILITY_SUBTREE_WILDCARD):
        subtree_rule = normalized_rule[: -len(CAPABILITY_SUBTREE_WILDCARD)] or "/"
        return _path_prefix_matches_rule(path, subtree_rule)
    if _is_path_template(normalized_rule):
        return _path_template_matches(path, normalized_rule)
    return _normalize_path(path) == normalized_rule


def _normalize_capability_rule(key: Any, capability: Any) -> tuple[str, str] | None:
    if not _capability_rule_input_is_text(key, capability):
        return None
    parsed_key = _parse_capability_rule_key(key)
    if parsed_key is None:
        return None
    method, path = parsed_key
    normalized_capability = capability.strip()
    if not _valid_capability_rule(method, path, normalized_capability):
        return None
    return f"{method} {path.rstrip('/') or '/'}", normalized_capability


def _capability_rule_input_is_text(key: Any, capability: Any) -> bool:
    return isinstance(key, str) and isinstance(capability, str)


def _parse_capability_rule_key(key: str) -> tuple[str, str] | None:
    parts = key.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    method, path = parts[0].upper(), parts[1].strip()
    return method, path


def _valid_capability_rule(method: str, path: str, capability: str) -> bool:
    return (
        method in CAPABILITY_RULE_METHODS
        and path.startswith("/")
        and len(path) <= 256
        and bool(capability)
        and len(capability) <= 128
    )


def _is_path_template(rule_path: str) -> bool:
    return "{" in rule_path and "}" in rule_path


def _path_template_matches(path: str, rule_path: str) -> bool:
    path_segments = _path_segments(path)
    rule_segments = _path_segments(rule_path)
    if len(path_segments) != len(rule_segments):
        return False
    for path_segment, rule_segment in zip(path_segments, rule_segments):
        if not _path_segment_matches_rule(path_segment, rule_segment):
            return False
    return True


def _path_prefix_matches_rule(path: str, rule_path: str) -> bool:
    path_segments = _path_segments(path)
    rule_segments = _path_segments(rule_path)
    if len(path_segments) < len(rule_segments):
        return False
    for path_segment, rule_segment in zip(path_segments, rule_segments):
        if not _path_segment_matches_rule(path_segment, rule_segment):
            return False
    return True


def _normalize_path(path: str) -> str:
    normalized = path.rstrip("/")
    return normalized or "/"


def _path_segments(path: str) -> list[str]:
    return [segment for segment in path.rstrip("/").split("/") if segment]


def _path_segment_matches_rule(path_segment: str, rule_segment: str) -> bool:
    if _is_template_segment(rule_segment):
        return bool(path_segment)
    return path_segment == rule_segment


def _is_template_segment(rule_segment: str) -> bool:
    return rule_segment.startswith("{") and rule_segment.endswith("}")


def _rules_by_specificity(rules: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(rules.items(), key=lambda item: len(item[0].split(maxsplit=1)[1]), reverse=True)


def build_enterprise_audit_middleware(
    *,
    runtime: EnterpriseReadinessRuntime,
    audit_emitter: AuditEmitter,
    component: SecurityAuditComponent | None = None,
    audit_store: SecurityAuditStore | None = None,
    audit_failure_is_fatal: bool | None = None,
    max_write_payload_bytes_resolver: MaxWritePayloadBytesResolver | None = None,
) -> MiddlewareCallable:
    async def middleware(request: Request, call_next: MiddlewareNext) -> Response:
        normalized_method = request.method.strip().upper()
        authorization = runtime.evaluate_request(
            normalized_method,
            request.url.path,
            dict(request.headers),
        )
        max_write_payload_bytes = runtime.env_integer(
            "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576
        )
        if max_write_payload_bytes_resolver is not None:
            max_write_payload_bytes = max_write_payload_bytes_resolver(
                request,
                max_write_payload_bytes,
            )
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if normalized_method in WRITE_METHODS and content_length > max_write_payload_bytes:
            event = _security_audit_event(
                runtime=runtime,
                component=component,
                request=request,
                authorization=authorization,
                decision=SecurityAuditDecision.DENY,
                reason=SecurityAuditReason.PAYLOAD_TOO_LARGE,
            )
            if not await _persist_security_audit(
                runtime=runtime,
                store=audit_store,
                event=event,
                failure_is_fatal=audit_failure_is_fatal,
            ):
                return _security_audit_unavailable_response()
            return JSONResponse(status_code=413, content={"detail": "payload_too_large"})

        if _is_unauthenticated_enterprise_path(request.url.path):
            response = await call_next(request)
            response.headers["X-Enterprise-Policy-Version"] = runtime.enterprise_policy_version()
            return response

        try:
            tenant_context = resolve_enterprise_tenant_context(
                tenant_id=request.headers.get("X-Tenant-Id"),
                actor_id=request.headers.get("X-Actor-Id"),
                role=request.headers.get("X-Role"),
                service_identity=request.headers.get("X-Service-Identity"),
                correlation_id=request_correlation_id(request.headers),
                identity_verified=authorization.principal is not None,
            )
        except TenantContextAdmissionError:
            event = _security_audit_event(
                runtime=runtime,
                component=component,
                request=request,
                authorization=authorization,
                decision=SecurityAuditDecision.DENY,
                reason=SecurityAuditReason.AUTHORIZATION_POLICY_DENIED,
            )
            if not await _persist_security_audit(
                runtime=runtime,
                store=audit_store,
                event=event,
                failure_is_fatal=audit_failure_is_fatal,
            ):
                return _security_audit_unavailable_response()
            return JSONResponse(
                status_code=401,
                media_type="application/problem+json",
                content=tenant_context_required_problem(
                    path=request.url.path,
                    correlation_id=request_correlation_id(request.headers),
                ),
            )
        request.state.tenant_context = tenant_context

        if not authorization.authorized:
            event = _security_audit_event(
                runtime=runtime,
                component=component,
                request=request,
                authorization=authorization,
                decision=SecurityAuditDecision.DENY,
                reason=SecurityAuditReason.AUTHORIZATION_POLICY_DENIED,
            )
            if not await _persist_security_audit(
                runtime=runtime,
                store=audit_store,
                event=event,
                failure_is_fatal=audit_failure_is_fatal,
            ):
                return _security_audit_unavailable_response()
            deny_correlation_id = request_correlation_id(request.headers)
            audit_emitter(
                action=f"DENY {normalized_method} {authorization.route_template}",
                actor_id=request_header_value(request.headers, "X-Actor-Id", "unknown"),
                tenant_id=tenant_context.tenant_id_text,
                role=request_header_value(request.headers, "X-Role", "unknown"),
                correlation_id=deny_correlation_id,
                metadata={"reason": authorization.reason},
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "authorization_policy_denied",
                    "reason": authorization.reason,
                },
            )

        audit_allowed_request = normalized_method in WRITE_METHODS or (
            normalized_method in READ_AUDIT_METHODS and _read_audit_required(runtime)
        )
        if audit_allowed_request:
            event = _security_audit_event(
                runtime=runtime,
                component=component,
                request=request,
                authorization=authorization,
                decision=SecurityAuditDecision.ALLOW,
                reason=SecurityAuditReason.AUTHORIZED,
            )
            if not await _persist_security_audit(
                runtime=runtime,
                store=audit_store,
                event=event,
                failure_is_fatal=audit_failure_is_fatal,
            ):
                return _security_audit_unavailable_response()

        if authorization.principal is not None:
            request.state.enterprise_verified_tenant_id = tenant_context.tenant_id_text

        response = await call_next(request)
        response.headers["X-Enterprise-Policy-Version"] = runtime.enterprise_policy_version()
        if normalized_method in WRITE_METHODS:
            write_correlation_id = request_correlation_id(
                request.headers, response.headers.get("X-Correlation-ID")
            )
            audit_emitter(
                action=f"{normalized_method} {authorization.route_template}",
                actor_id=request_header_value(request.headers, "X-Actor-Id", "unknown"),
                tenant_id=tenant_context.tenant_id_text,
                role=request_header_value(request.headers, "X-Role", "unknown"),
                correlation_id=write_correlation_id,
                metadata={"status_code": response.status_code},
            )
        elif normalized_method in READ_AUDIT_METHODS and _read_audit_required(runtime):
            read_correlation_id = request_correlation_id(
                request.headers, response.headers.get("X-Correlation-ID")
            )
            audit_emitter(
                action=f"{normalized_method} {authorization.route_template}",
                actor_id=request_header_value(request.headers, "X-Actor-Id", "unknown"),
                tenant_id=tenant_context.tenant_id_text,
                role=request_header_value(request.headers, "X-Role", "unknown"),
                correlation_id=read_correlation_id,
                metadata={"status_code": response.status_code, "access_type": "read"},
            )
        return response

    return middleware


def _read_audit_required(runtime: EnterpriseReadinessRuntime) -> bool:
    return (
        runtime.env_enabled("ENTERPRISE_AUDIT_READS", "false")
        or not explicit_local_config_profile_enabled()
    )


async def _persist_security_audit(
    *,
    runtime: EnterpriseReadinessRuntime,
    store: SecurityAuditStore | None,
    event: SecurityAuditEvent | None,
    failure_is_fatal: bool | None,
) -> bool:
    if store is None or event is None:
        return True
    try:
        await store.append(event)
        observe_security_audit_delivery(service=event.component.value, outcome="delivered")
        return True
    except InfrastructureAuditWriteFailed:
        observe_security_audit_delivery(service=event.component.value, outcome="failed")
        runtime.logger.warning(
            "enterprise_security_audit_persistence_failed",
            extra={"reason_code": "audit_persistence_failed"},
        )
        should_fail = (
            not explicit_local_config_profile_enabled()
            if failure_is_fatal is None
            else failure_is_fatal
        )
        return not should_fail


def _security_audit_event(
    *,
    runtime: EnterpriseReadinessRuntime,
    component: SecurityAuditComponent | None,
    request: Request,
    authorization: EnterpriseAuthorizationDecision,
    decision: SecurityAuditDecision,
    reason: SecurityAuditReason,
) -> SecurityAuditEvent | None:
    if component is None:
        return None
    principal = authorization.principal
    normalized_headers = _normalize_headers(dict(request.headers))
    identity_verified = principal is not None
    return SecurityAuditEvent(
        event_id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc),
        component=component,
        route_template=authorization.route_template,
        method=SecurityAuditMethod(request.method.strip().upper()),
        decision=decision,
        reason=reason,
        required_capability=authorization.required_capability,
        service_identity=principal.service_identity if principal is not None else None,
        actor_id=normalized_headers.get("x-actor-id") if identity_verified else None,
        tenant_id=normalized_headers.get("x-tenant-id") if identity_verified else None,
        role=normalized_headers.get("x-role") if identity_verified else None,
        identity_posture=(
            SecurityAuditIdentityPosture.VERIFIED
            if identity_verified
            else SecurityAuditIdentityPosture.UNVERIFIED
        ),
        correlation_id=request_correlation_id(request.headers),
        trace_id=request_trace_id(request.headers),
        policy_version=runtime.enterprise_policy_version(),
    )


def _security_audit_unavailable_response() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "security_audit_unavailable"})


def _is_unauthenticated_enterprise_path(path: str) -> bool:
    return _normalize_path(path) in ENTERPRISE_UNAUTHENTICATED_PATHS
