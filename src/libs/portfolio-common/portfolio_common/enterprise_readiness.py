"""Shared enterprise readiness policy, authorization, and audit helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from portfolio_common.logging_utils import (
    correlation_id_var,
    normalize_lineage_value,
    redact_sensitive,
)
from portfolio_common.runtime_settings import (
    env_bool,
    env_int,
    env_json_map,
    env_str,
    production_security_profile_enabled,
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


class EnterpriseSettings(Protocol):
    enterprise_policy_version: str
    enterprise_primary_key_id: str
    enterprise_enforce_authz: bool
    enterprise_enforce_read_authz: bool
    enterprise_audit_reads: bool
    enterprise_require_capability_rules: bool
    enterprise_enforce_runtime_config: bool
    enterprise_secret_rotation_days: int
    enterprise_max_write_payload_bytes: int
    enterprise_feature_flags: dict[str, Any]
    enterprise_capability_rules: dict[str, Any]


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
    enterprise_feature_flags: dict[str, Any]
    enterprise_capability_rules: dict[str, Any]


@dataclass(frozen=True)
class EnterpriseReadinessRuntime:
    service_name: str
    load_settings: Callable[[], EnterpriseSettings]
    env_bool: Callable[[str, bool], bool]
    env_int: Callable[[str, int], int]
    logger: logging.Logger

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
        _append_issue_if(
            issues,
            "missing_policy_version",
            not self.enterprise_policy_version().strip(),
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
            "missing_primary_key_id",
            authz_enabled and not self.load_settings().enterprise_primary_key_id.strip(),
        )
        _append_issue_if(
            issues,
            "missing_capability_rules",
            self._requires_capability_rules(authz_enabled) and not self.load_capability_rules(),
        )

        if issues and self.env_enabled("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "false"):
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

    def authorize_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> tuple[bool, str | None]:
        normalized_method = method.strip().upper()
        required_capability = self.required_capability(normalized_method, path)
        if not self._request_requires_authorization(normalized_method, required_capability):
            return True, None

        normalized_headers = _normalize_headers(headers)
        missing_headers = _missing_required_headers(normalized_headers)
        if missing_headers:
            return False, f"missing_headers:{','.join(missing_headers)}"

        if not _has_service_identity(normalized_headers):
            return False, "missing_service_identity"

        return self._authorize_required_capability(required_capability, normalized_headers)

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
        normalized_headers: dict[str, str],
    ) -> tuple[bool, str | None]:
        if not required_capability and self.env_enabled(
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false"
        ):
            return False, "missing_capability_rule"
        if required_capability:
            capabilities = _capabilities_from_headers(normalized_headers)
            if required_capability not in capabilities:
                return False, f"missing_capability:{required_capability}"

        return True, None

    def required_capability(self, method: str, path: str) -> str | None:
        method = method.strip().upper()
        for key, capability in _rules_by_specificity(self.load_capability_rules()):
            prefix = f"{method} "
            if key.upper().startswith(prefix) and _path_matches_rule(path, key[len(prefix) :]):
                return capability
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
        load_settings=lambda: load_default_enterprise_settings(service_name=service_name),
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
        max_write_payload_bytes_resolver=max_write_payload_bytes_resolver,
    )


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


def _path_matches_rule(path: str, rule_path: str) -> bool:
    normalized_rule = rule_path.rstrip("/")
    if not normalized_rule or normalized_rule == "/":
        return True
    if _is_path_template(normalized_rule):
        return _path_template_matches(path, normalized_rule)
    return path == normalized_rule or path.startswith(f"{normalized_rule}/")


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
    return method in CAPABILITY_RULE_METHODS and path.startswith("/") and bool(capability)


def _is_path_template(rule_path: str) -> bool:
    return "{" in rule_path and "}" in rule_path


def _path_template_matches(path: str, rule_path: str) -> bool:
    path_segments = _path_segments(path)
    rule_segments = _path_segments(rule_path)
    if len(path_segments) < len(rule_segments):
        return False
    for path_segment, rule_segment in zip(path_segments, rule_segments):
        if not _path_segment_matches_rule(path_segment, rule_segment):
            return False
    return True


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
    max_write_payload_bytes_resolver: MaxWritePayloadBytesResolver | None = None,
) -> MiddlewareCallable:
    async def middleware(request: Request, call_next: MiddlewareNext) -> Response:
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
        if request.method in WRITE_METHODS and content_length > max_write_payload_bytes:
            return JSONResponse(status_code=413, content={"detail": "payload_too_large"})

        authorized, reason = runtime.authorize_request(
            request.method, request.url.path, dict(request.headers)
        )
        if not authorized:
            deny_correlation_id = _request_correlation_id(request)
            audit_emitter(
                action=f"DENY {request.method} {request.url.path}",
                actor_id=_request_header_value(request, "X-Actor-Id", "unknown"),
                tenant_id=_request_header_value(request, "X-Tenant-Id", "default"),
                role=_request_header_value(request, "X-Role", "unknown"),
                correlation_id=deny_correlation_id,
                metadata={"reason": reason},
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "authorization_policy_denied", "reason": reason},
            )

        response = await call_next(request)
        response.headers["X-Enterprise-Policy-Version"] = runtime.enterprise_policy_version()
        if request.method in WRITE_METHODS:
            write_correlation_id = _request_correlation_id(
                request, response.headers.get("X-Correlation-ID")
            )
            audit_emitter(
                action=f"{request.method} {request.url.path}",
                actor_id=_request_header_value(request, "X-Actor-Id", "unknown"),
                tenant_id=_request_header_value(request, "X-Tenant-Id", "default"),
                role=_request_header_value(request, "X-Role", "unknown"),
                correlation_id=write_correlation_id,
                metadata={"status_code": response.status_code},
            )
        elif request.method in READ_AUDIT_METHODS and runtime.env_enabled(
            "ENTERPRISE_AUDIT_READS", "false"
        ):
            read_correlation_id = _request_correlation_id(
                request, response.headers.get("X-Correlation-ID")
            )
            audit_emitter(
                action=f"{request.method} {request.url.path}",
                actor_id=_request_header_value(request, "X-Actor-Id", "unknown"),
                tenant_id=_request_header_value(request, "X-Tenant-Id", "default"),
                role=_request_header_value(request, "X-Role", "unknown"),
                correlation_id=read_correlation_id,
                metadata={"status_code": response.status_code, "access_type": "read"},
            )
        return response

    return middleware


def _request_header_value(request: Request, name: str, default: str) -> str:
    value = request.headers.get(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def _request_correlation_id(
    request: Request, response_correlation_id: str | None = None
) -> str | None:
    return normalize_lineage_value(
        request.headers.get("X-Correlation-Id")
        or request.headers.get("X-Correlation-ID")
        or response_correlation_id
        or correlation_id_var.get()
    )
