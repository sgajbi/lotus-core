import logging
from typing import Any, Callable

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

SERVICE_NAME = "ingestion_service"
logger = logging.getLogger("enterprise_readiness")

INGESTION_WRITE_CAPABILITY_RULES: dict[str, str] = {
    "POST /ingest/portfolios": "ingestion.portfolios.write",
    "POST /ingest/transaction": "ingestion.transactions.write",
    "POST /ingest/transactions": "ingestion.transactions.write",
    "POST /ingest/instruments": "ingestion.instruments.write",
    "POST /ingest/market-prices": "ingestion.market_prices.write",
    "POST /ingest/fx-rates": "ingestion.fx_rates.write",
    "POST /ingest/business-dates": "ingestion.business_dates.write",
    "POST /ingest/portfolio-bundle": "ingestion.portfolio_bundle.write",
    "POST /ingest/uploads/preview": "ingestion.uploads.write",
    "POST /ingest/uploads/commit": "ingestion.uploads.write",
    "POST /reprocess/transactions": "ingestion.reprocessing.write",
    "POST /ingest/benchmark-assignments": "ingestion.reference_data.write",
    "POST /ingest/model-portfolios": "ingestion.reference_data.write",
    "POST /ingest/model-portfolio-targets": "ingestion.reference_data.write",
    "POST /ingest/instrument-eligibility": "ingestion.reference_data.write",
    "POST /ingest/mandate-bindings": "ingestion.reference_data.write",
    "POST /ingest/client-restriction-profiles": "ingestion.reference_data.write",
    "POST /ingest/sustainability-preferences": "ingestion.reference_data.write",
    "POST /ingest/client-tax-profiles": "ingestion.reference_data.write",
    "POST /ingest/client-tax-rule-sets": "ingestion.reference_data.write",
    "POST /ingest/client-income-needs-schedules": "ingestion.reference_data.write",
    "POST /ingest/liquidity-reserve-requirements": "ingestion.reference_data.write",
    "POST /ingest/planned-withdrawal-schedules": "ingestion.reference_data.write",
    "POST /ingest/benchmark-definitions": "ingestion.reference_data.write",
    "POST /ingest/benchmark-compositions": "ingestion.reference_data.write",
    "POST /ingest/indices": "ingestion.reference_data.write",
    "POST /ingest/index-price-series": "ingestion.reference_data.write",
    "POST /ingest/index-return-series": "ingestion.reference_data.write",
    "POST /ingest/benchmark-return-series": "ingestion.reference_data.write",
    "POST /ingest/risk-free-series": "ingestion.reference_data.write",
    "POST /ingest/reference/classification-taxonomy": "ingestion.reference_data.write",
    "POST /ingest/reference/cash-accounts": "ingestion.reference_data.write",
    "POST /ingest/reference/instrument-lookthrough-components": ("ingestion.reference_data.write"),
}


def ingestion_write_capability_rules() -> dict[str, str]:
    return dict(INGESTION_WRITE_CAPABILITY_RULES)


_runtime = EnterpriseReadinessRuntime(
    service_name=SERVICE_NAME,
    load_settings=lambda: load_default_enterprise_settings(service_name=SERVICE_NAME),
    env_bool=lambda name, default: env_bool(name, default, service_name=SERVICE_NAME),
    env_int=lambda name, default: env_int(name, default, service_name=SERVICE_NAME),
    logger=logger,
    default_capability_rules=ingestion_write_capability_rules,
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
        max_write_payload_bytes_resolver=None,
    )


def build_ingestion_enterprise_audit_middleware(
    *, max_write_payload_bytes_resolver: Callable[[], int] | None
) -> MiddlewareCallable:
    return build_shared_enterprise_audit_middleware(
        runtime=_runtime,
        audit_emitter=lambda **kwargs: emit_audit_event(**kwargs),
        max_write_payload_bytes_resolver=max_write_payload_bytes_resolver,
    )
