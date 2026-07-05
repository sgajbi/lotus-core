import logging
from typing import Any

from portfolio_common.enterprise_readiness import (
    EnterpriseReadinessRuntime,
    MiddlewareCallable,
    load_default_enterprise_settings,
)
from portfolio_common.enterprise_readiness import (
    build_enterprise_audit_middleware as build_shared_enterprise_audit_middleware,
)
from portfolio_common.enterprise_readiness import (
    redact_sensitive as shared_redact_sensitive,
)
from portfolio_common.runtime_settings import env_bool, env_int

SERVICE_NAME = "financial_reconciliation_service"
logger = logging.getLogger("enterprise_readiness")

FINANCIAL_RECONCILIATION_CAPABILITY_RULES: dict[str, str] = {
    "POST /reconciliation/runs/transaction-cashflow": ("financial_reconciliation.controls.run"),
    "POST /reconciliation/runs/position-valuation": "financial_reconciliation.controls.run",
    "POST /reconciliation/runs/timeseries-integrity": ("financial_reconciliation.controls.run"),
    "GET /reconciliation/runs": "financial_reconciliation.controls.read",
    "GET /reconciliation/runs/{run_id}": "financial_reconciliation.controls.read",
    "GET /reconciliation/runs/{run_id}/findings": ("financial_reconciliation.controls.read"),
}


def financial_reconciliation_capability_rules() -> dict[str, str]:
    return dict(FINANCIAL_RECONCILIATION_CAPABILITY_RULES)


_runtime = EnterpriseReadinessRuntime(
    service_name=SERVICE_NAME,
    load_settings=lambda: load_default_enterprise_settings(service_name=SERVICE_NAME),
    env_bool=lambda name, default: env_bool(name, default, service_name=SERVICE_NAME),
    env_int=lambda name, default: env_int(name, default, service_name=SERVICE_NAME),
    logger=logger,
    default_capability_rules=financial_reconciliation_capability_rules,
)


def enterprise_policy_version() -> str:
    return _runtime.enterprise_policy_version()


def validate_enterprise_runtime_config() -> list[str]:
    return _runtime.validate_enterprise_runtime_config()


def load_capability_rules() -> dict[str, str]:
    return _runtime.load_capability_rules()


def redact_sensitive(value: Any) -> Any:
    return shared_redact_sensitive(value)


def _required_capability(method: str, path: str) -> str | None:
    return _runtime.required_capability(method, path)


def authorize_request(method: str, path: str, headers: dict[str, str]) -> tuple[bool, str | None]:
    return _runtime.authorize_request(method, path, headers)


def authorize_write_request(
    method: str, path: str, headers: dict[str, str]
) -> tuple[bool, str | None]:
    return _runtime.authorize_write_request(method, path, headers)


def authorize_capability(
    headers: dict[str, str],
    required_capability: str,
) -> tuple[bool, str | None]:
    return _runtime.authorize_capability(headers, required_capability)


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
