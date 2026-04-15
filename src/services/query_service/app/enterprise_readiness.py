import logging
from typing import Any

from portfolio_common.enterprise_readiness import (
    EnterpriseReadinessRuntime,
    MiddlewareCallable,
    build_enterprise_audit_middleware as build_shared_enterprise_audit_middleware,
    redact_sensitive as shared_redact_sensitive,
)

from .settings import env_bool, env_int, load_query_service_settings

logger = logging.getLogger("enterprise_readiness")

_SERVICE_NAME = "lotus-core"
_runtime = EnterpriseReadinessRuntime(
    service_name=_SERVICE_NAME,
    load_settings=load_query_service_settings,
    env_bool=env_bool,
    env_int=env_int,
    logger=logger,
)


def _env_enabled(name: str, default: str = "true") -> bool:
    return _runtime.env_enabled(name, default)


def _load_json_map(name: str) -> dict[str, Any]:
    if name not in {"ENTERPRISE_FEATURE_FLAGS_JSON", "ENTERPRISE_CAPABILITY_RULES_JSON"}:
        return {}
    return _runtime.load_json_map(name)


def _env_int(name: str, default: int) -> int:
    return env_int(name, default)


def enterprise_policy_version() -> str:
    return _runtime.enterprise_policy_version()


def validate_enterprise_runtime_config() -> list[str]:
    return _runtime.validate_enterprise_runtime_config()


def load_feature_flags() -> dict[str, dict[str, dict[str, bool]]]:
    return _runtime.load_feature_flags()


def load_capability_rules() -> dict[str, str]:
    return _runtime.load_capability_rules()


def redact_sensitive(value: Any) -> Any:
    return shared_redact_sensitive(value)


def is_feature_enabled(feature_key: str, tenant_id: str, role: str) -> bool:
    return _runtime.is_feature_enabled(feature_key, tenant_id, role)


def _required_capability(method: str, path: str) -> str | None:
    return _runtime.required_capability(method, path)


def authorize_request(method: str, path: str, headers: dict[str, str]) -> tuple[bool, str | None]:
    return _runtime.authorize_request(method, path, headers)


def authorize_write_request(
    method: str, path: str, headers: dict[str, str]
) -> tuple[bool, str | None]:
    return _runtime.authorize_write_request(method, path, headers)


def emit_audit_event(
    *,
    action: str,
    actor_id: str,
    tenant_id: str,
    role: str,
    correlation_id: str | None,
    metadata: dict[str, Any],
) -> None:
    _runtime.emit_audit_event(
        action=action,
        actor_id=actor_id,
        tenant_id=tenant_id,
        role=role,
        correlation_id=correlation_id,
        metadata=metadata,
    )


def build_enterprise_audit_middleware() -> MiddlewareCallable:
    return build_shared_enterprise_audit_middleware(
        runtime=_runtime,
        audit_emitter=lambda **kwargs: emit_audit_event(**kwargs),
    )
