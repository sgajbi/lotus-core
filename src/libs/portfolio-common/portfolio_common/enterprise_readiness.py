"""Shared enterprise readiness policy, authorization, and audit helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.source_data_security import source_data_capability_rules

MiddlewareNext = Callable[[Request], Awaitable[Response]]
MiddlewareCallable = Callable[[Request, MiddlewareNext], Awaitable[Response]]
AuditEmitter = Callable[..., None]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_AUDIT_METHODS = {"GET", "HEAD"}
READ_AUTHZ_METHODS = {"GET", "HEAD"}
CAPABILITY_RULE_METHODS = WRITE_METHODS | READ_AUTHZ_METHODS
REQUIRED_HEADERS = {"x-actor-id", "x-tenant-id", "x-role", "x-correlation-id"}
REDACT_FIELDS = {
    "password",
    "secret",
    "token",
    "authorization",
    "ssn",
    "account_number",
    "client_email",
}


class EnterpriseSettings(Protocol):
    enterprise_policy_version: str
    enterprise_primary_key_id: str
    enterprise_enforce_authz: bool
    enterprise_enforce_read_authz: bool
    enterprise_audit_reads: bool
    enterprise_require_capability_rules: bool
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
        }.get(name)
        if settings_attr:
            return bool(getattr(self.load_settings(), settings_attr))
        return self.env_bool(name, default.strip().lower() in {"1", "true", "yes", "on"})

    def env_integer(self, name: str, default: int) -> int:
        settings_attr = {
            "ENTERPRISE_SECRET_ROTATION_DAYS": "enterprise_secret_rotation_days",
            "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES": "enterprise_max_write_payload_bytes",
        }.get(name)
        if settings_attr:
            return int(getattr(self.load_settings(), settings_attr))
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
        if not self.enterprise_policy_version().strip():
            issues.append("missing_policy_version")

        rotation_days = self.env_integer("ENTERPRISE_SECRET_ROTATION_DAYS", 90)
        if rotation_days <= 0 or rotation_days > 90:
            issues.append("secret_rotation_days_out_of_range")

        max_write_payload_bytes = self.env_integer("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576)
        if max_write_payload_bytes <= 0:
            issues.append("max_write_payload_bytes_out_of_range")

        if (
            self.env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false")
            or self.env_enabled("ENTERPRISE_ENFORCE_READ_AUTHZ", "false")
        ) and not self.load_settings().enterprise_primary_key_id.strip():
            issues.append("missing_primary_key_id")
        if (
            self.env_enabled("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false")
            and (
                self.env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false")
                or self.env_enabled("ENTERPRISE_ENFORCE_READ_AUTHZ", "false")
            )
            and not self.load_capability_rules()
        ):
            issues.append("missing_capability_rules")

        if issues and self.env_enabled("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "false"):
            raise RuntimeError(f"enterprise_runtime_config_invalid:{','.join(issues)}")
        return issues

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
        feature = flags.get(feature_key, {})
        if not isinstance(feature, dict):
            return False
        tenant = feature.get(tenant_id, {})
        if not isinstance(tenant, dict):
            return False
        if isinstance(tenant.get(role), bool):
            return tenant[role]
        if isinstance(tenant.get("*"), bool):
            return tenant["*"]
        global_entry = feature.get("*", {})
        if not isinstance(global_entry, dict):
            return False
        global_default = global_entry.get("*")
        return bool(global_default) if isinstance(global_default, bool) else False

    def authorize_write_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> tuple[bool, str | None]:
        return self.authorize_request(method, path, headers)

    def authorize_request(
        self, method: str, path: str, headers: dict[str, str]
    ) -> tuple[bool, str | None]:
        normalized_method = method.upper()
        required_capability = self.required_capability(normalized_method, path)
        requires_write_authz = normalized_method in WRITE_METHODS and self.env_enabled(
            "ENTERPRISE_ENFORCE_AUTHZ", "false"
        )
        requires_read_authz = (
            normalized_method in READ_AUTHZ_METHODS or required_capability is not None
        ) and self.env_enabled(
            "ENTERPRISE_ENFORCE_READ_AUTHZ",
            "false",
        )
        if not (requires_write_authz or requires_read_authz):
            return True, None

        normalized = {str(k).lower(): str(v).strip() for k, v in headers.items()}
        missing = sorted(header for header in REQUIRED_HEADERS if not normalized.get(header))
        if missing:
            return False, f"missing_headers:{','.join(missing)}"

        if not (normalized.get("x-service-identity") or normalized.get("authorization")):
            return False, "missing_service_identity"

        if not required_capability and self.env_enabled(
            "ENTERPRISE_REQUIRE_CAPABILITY_RULES", "false"
        ):
            return False, "missing_capability_rule"
        if required_capability:
            capabilities = {
                part.strip()
                for part in normalized.get("x-capabilities", "").split(",")
                if part.strip()
            }
            if required_capability not in capabilities:
                return False, f"missing_capability:{required_capability}"

        return True, None

    def required_capability(self, method: str, path: str) -> str | None:
        method = method.upper()
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


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in REDACT_FIELDS:
                result[key] = "***REDACTED***"
            else:
                result[key] = redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def _path_matches_rule(path: str, rule_path: str) -> bool:
    normalized_rule = rule_path.rstrip("/")
    if not normalized_rule or normalized_rule == "/":
        return True
    if "{" in normalized_rule and "}" in normalized_rule:
        return _path_template_matches(path, normalized_rule)
    return path == normalized_rule or path.startswith(f"{normalized_rule}/")


def _normalize_capability_rule(key: Any, capability: Any) -> tuple[str, str] | None:
    if not isinstance(key, str) or not isinstance(capability, str):
        return None
    parts = key.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    method, path = parts[0].upper(), parts[1].strip()
    normalized_capability = capability.strip()
    if (
        method not in CAPABILITY_RULE_METHODS
        or not path.startswith("/")
        or not normalized_capability
    ):
        return None
    return f"{method} {path.rstrip('/') or '/'}", normalized_capability


def _path_template_matches(path: str, rule_path: str) -> bool:
    path_segments = [segment for segment in path.rstrip("/").split("/") if segment]
    rule_segments = [segment for segment in rule_path.rstrip("/").split("/") if segment]
    if len(path_segments) < len(rule_segments):
        return False
    for path_segment, rule_segment in zip(path_segments, rule_segments):
        if rule_segment.startswith("{") and rule_segment.endswith("}"):
            if not path_segment:
                return False
            continue
        if path_segment != rule_segment:
            return False
    return True


def _rules_by_specificity(rules: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(rules.items(), key=lambda item: len(item[0].split(maxsplit=1)[1]), reverse=True)


def build_enterprise_audit_middleware(
    *,
    runtime: EnterpriseReadinessRuntime,
    audit_emitter: AuditEmitter,
) -> MiddlewareCallable:
    async def middleware(request: Request, call_next: MiddlewareNext) -> Response:
        max_write_payload_bytes = runtime.env_integer(
            "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576
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
