import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from portfolio_common.logging_utils import correlation_id_var

from src.services.query_service.app.settings import (
    env_bool,
    env_int,
    load_query_service_settings,
)

logger = logging.getLogger("enterprise_readiness")
MiddlewareNext = Callable[[Request], Awaitable[Response]]
MiddlewareCallable = Callable[[Request, MiddlewareNext], Awaitable[Response]]

_SERVICE_NAME = "lotus-core"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_REQUIRED_HEADERS = {"x-actor-id", "x-tenant-id", "x-role", "x-correlation-id"}
_REDACT_FIELDS = {
    "password",
    "secret",
    "token",
    "authorization",
    "ssn",
    "account_number",
    "client_email",
}


def _env_enabled(name: str, default: str = "true") -> bool:
    return env_bool(name, default.strip().lower() in {"1", "true", "yes", "on"})


def _load_json_map(name: str) -> dict[str, Any]:
    settings = load_query_service_settings()
    if name == "ENTERPRISE_FEATURE_FLAGS_JSON":
        parsed = settings.enterprise_feature_flags
        return parsed if isinstance(parsed, dict) else {}
    if name == "ENTERPRISE_CAPABILITY_RULES_JSON":
        parsed = settings.enterprise_capability_rules
        return parsed if isinstance(parsed, dict) else {}
    raw = "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _env_int(name: str, default: int) -> int:
    return env_int(name, default)


def enterprise_policy_version() -> str:
    return load_query_service_settings().enterprise_policy_version


def validate_enterprise_runtime_config() -> list[str]:
    issues: list[str] = []
    if not enterprise_policy_version().strip():
        issues.append("missing_policy_version")

    rotation_days = _env_int("ENTERPRISE_SECRET_ROTATION_DAYS", 90)
    if rotation_days <= 0 or rotation_days > 90:
        issues.append("secret_rotation_days_out_of_range")

    if (
        _env_enabled("ENTERPRISE_ENFORCE_AUTHZ", "false")
        and not load_query_service_settings().enterprise_primary_key_id.strip()
    ):
        issues.append("missing_primary_key_id")

    if issues and _env_enabled("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "false"):
        raise RuntimeError(f"enterprise_runtime_config_invalid:{','.join(issues)}")
    return issues


def load_feature_flags() -> dict[str, dict[str, dict[str, bool]]]:
    return _load_json_map("ENTERPRISE_FEATURE_FLAGS_JSON")


def load_capability_rules() -> dict[str, str]:
    rules = _load_json_map("ENTERPRISE_CAPABILITY_RULES_JSON")
    return {str(key): str(value) for key, value in rules.items() if isinstance(key, str)}


def is_feature_enabled(feature_key: str, tenant_id: str, role: str) -> bool:
    flags = load_feature_flags()
    feature = flags.get(feature_key, {})
    tenant = feature.get(tenant_id, {})
    if isinstance(tenant.get(role), bool):
        return tenant[role]
    if isinstance(tenant.get("*"), bool):
        return tenant["*"]
    global_default = feature.get("*", {}).get("*")
    return bool(global_default) if isinstance(global_default, bool) else False


def _required_capability(method: str, path: str) -> str | None:
    method = method.upper()
    for key, capability in load_capability_rules().items():
        prefix = f"{method} "
        if key.upper().startswith(prefix) and path.startswith(key[len(prefix) :]):
            return capability
    return None


def authorize_write_request(
    method: str, path: str, headers: dict[str, str]
) -> tuple[bool, str | None]:
    if method.upper() not in _WRITE_METHODS or not _env_enabled(
        "ENTERPRISE_ENFORCE_AUTHZ", "false"
    ):
        return True, None

    normalized = {str(k).lower(): str(v) for k, v in headers.items()}
    missing = sorted(header for header in _REQUIRED_HEADERS if not normalized.get(header))
    if missing:
        return False, f"missing_headers:{','.join(missing)}"

    if not (normalized.get("x-service-identity") or normalized.get("authorization")):
        return False, "missing_service_identity"

    required_capability = _required_capability(method, path)
    if required_capability:
        capabilities = {
            part.strip() for part in normalized.get("x-capabilities", "").split(",") if part.strip()
        }
        if required_capability not in capabilities:
            return False, f"missing_capability:{required_capability}"

    return True, None


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in _REDACT_FIELDS:
                result[key] = "***REDACTED***"
            else:
                result[key] = redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def emit_audit_event(
    *,
    action: str,
    actor_id: str,
    tenant_id: str,
    role: str,
    correlation_id: str | None,
    metadata: dict[str, Any],
) -> None:
    logger.info(
        "enterprise_audit_event",
        extra={
            "audit": {
                "service": _SERVICE_NAME,
                "action": action,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "role": role,
                "correlation_id": correlation_id or "",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "policy_version": enterprise_policy_version(),
                "metadata": redact_sensitive(metadata),
            }
        },
    )


def build_enterprise_audit_middleware() -> MiddlewareCallable:
    async def middleware(request: Request, call_next: MiddlewareNext) -> Response:
        max_write_payload_bytes = _env_int("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", 1_048_576)
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if request.method in _WRITE_METHODS and content_length > max_write_payload_bytes:
            return JSONResponse(status_code=413, content={"detail": "payload_too_large"})

        authorized, reason = authorize_write_request(
            request.method, request.url.path, dict(request.headers)
        )
        if not authorized:
            deny_correlation_id = (
                request.headers.get("X-Correlation-Id")
                or request.headers.get("X-Correlation-ID")
                or correlation_id_var.get()
            )
            emit_audit_event(
                action=f"DENY {request.method} {request.url.path}",
                actor_id=request.headers.get("X-Actor-Id", "unknown"),
                tenant_id=request.headers.get("X-Tenant-Id", "default"),
                role=request.headers.get("X-Role", "unknown"),
                correlation_id=deny_correlation_id,
                metadata={"reason": reason},
            )
            return JSONResponse(
                status_code=403, content={"detail": "authorization_policy_denied", "reason": reason}
            )

        response = await call_next(request)
        response.headers["X-Enterprise-Policy-Version"] = enterprise_policy_version()
        if request.method in _WRITE_METHODS:
            write_correlation_id = (
                request.headers.get("X-Correlation-Id")
                or request.headers.get("X-Correlation-ID")
                or response.headers.get("X-Correlation-ID")
                or correlation_id_var.get()
            )
            emit_audit_event(
                action=f"{request.method} {request.url.path}",
                actor_id=request.headers.get("X-Actor-Id", "unknown"),
                tenant_id=request.headers.get("X-Tenant-Id", "default"),
                role=request.headers.get("X-Role", "unknown"),
                correlation_id=write_correlation_id,
                metadata={"status_code": response.status_code},
            )
        return response

    return middleware
