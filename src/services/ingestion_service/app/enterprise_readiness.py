import logging
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from portfolio_common.domain.security_audit import SecurityAuditComponent
from portfolio_common.enterprise_readiness import (
    EnterpriseReadinessRuntime,
    MiddlewareCallable,
    create_runtime_security_audit_store,
    load_default_enterprise_settings,
)
from portfolio_common.enterprise_readiness import (
    build_enterprise_audit_middleware as build_shared_enterprise_audit_middleware,
)
from portfolio_common.enterprise_readiness import (
    redact_sensitive as shared_redact_sensitive,
)
from portfolio_common.portfolio_financial_source_cut_admission import closed_source_json
from portfolio_common.runtime_settings import env_bool, env_int

SERVICE_NAME = "ingestion_service"
logger = logging.getLogger("enterprise_readiness")

NEUTRAL_SOURCE_WRITE_ENDPOINTS = frozenset(
    {
        "/ingest/portfolio-historical-registry-chunks",
        "/ingest/portfolio-historical-registry-cuts",
        "/ingest/portfolio-financial-source-cut-chunks",
        "/ingest/portfolio-financial-source-cuts",
    }
)

INGESTION_WRITE_CAPABILITY_RULES: dict[str, str] = {
    "POST /ingest/portfolio-historical-registry-chunks": (
        "ingestion.portfolio_historical_registries.write"
    ),
    "POST /ingest/portfolio-historical-registry-cuts": (
        "ingestion.portfolio_historical_registries.write"
    ),
    "POST /ingest/portfolio-financial-source-cut-chunks": (
        "ingestion.portfolio_financial_source_cuts.write"
    ),
    "POST /ingest/portfolio-financial-source-cuts": (
        "ingestion.portfolio_financial_source_cuts.write"
    ),
    "POST /ingest/portfolio-flow-event-observations": (
        "ingestion.portfolio_flow_event_observations.write"
    ),
    "POST /ingest/portfolio-flow-source-cuts": "ingestion.portfolio_flow_source_cuts.write",
    "POST /ingest/portfolio-cash-availability-observations": (
        "ingestion.portfolio_cash_availability_observations.write"
    ),
    "POST /ingest/portfolio-funding-investment-observations": (
        "ingestion.portfolio_funding_investment_observations.write"
    ),
    "POST /ingest/portfolios": "ingestion.portfolios.write",
    "POST /ingest/transaction": "ingestion.transactions.write",
    "POST /ingest/transactions": "ingestion.transactions.write",
    "POST /ingest/transactions/{transaction_id}/source-evidence": (
        "ingestion.transactions.source_evidence.correct"
    ),
    "POST /ingest/instruments": "ingestion.instruments.write",
    "POST /ingest/market-prices": "ingestion.market_prices.write",
    "POST /ingest/authoritative-market-price-source-facts": (
        "ingestion.market_prices.authority.write"
    ),
    "POST /ingest/fixed-income-book-cost-authorities": (
        "ingestion.fixed_income_book_cost.authority.write"
    ),
    "POST /ingest/corporate-action-manifests": ("ingestion.corporate_actions.manifest.write"),
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
    "POST /ingest/instrument-valuation-policy-assignments": "ingestion.reference_data.write",
    "POST /ingest/mandate-bindings": "ingestion.reference_data.write",
    "POST /ingest/client-restriction-profiles": "ingestion.reference_data.write",
    "POST /ingest/sustainability-preferences": "ingestion.reference_data.write",
    "POST /ingest/client-tax-profiles": "ingestion.reference_data.write",
    "POST /ingest/client-tax-rule-sets": "ingestion.reference_data.write",
    "POST /ingest/client-income-needs-schedules": "ingestion.reference_data.write",
    "POST /ingest/liquidity-reserve-requirements": "ingestion.reference_data.write",
    "POST /ingest/planned-withdrawal-schedules": "ingestion.reference_data.write",
    "POST /ingest/portfolio-party-role-assignments": "ingestion.reference_data.write",
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
        component=SecurityAuditComponent.INGESTION,
        audit_store=create_runtime_security_audit_store(service_name=SERVICE_NAME),
        max_write_payload_bytes_resolver=None,
    )


def build_ingestion_enterprise_audit_middleware(
    *, max_write_payload_bytes_resolver: Callable[[Request, int], int] | None
) -> MiddlewareCallable:
    shared = build_shared_enterprise_audit_middleware(
        runtime=_runtime,
        audit_emitter=lambda **kwargs: emit_audit_event(**kwargs),
        component=SecurityAuditComponent.INGESTION,
        audit_store=create_runtime_security_audit_store(service_name=SERVICE_NAME),
        max_write_payload_bytes_resolver=max_write_payload_bytes_resolver,
    )

    async def middleware(request, call_next):
        async def admitted_call_next(admitted_request):
            if (
                admitted_request.method == "POST"
                and admitted_request.url.path in NEUTRAL_SOURCE_WRITE_ENDPOINTS
            ):
                refusal = await buffer_neutral_source_body(admitted_request)
                if refusal is not None:
                    return refusal
            return await call_next(admitted_request)

        return await shared(request, admitted_call_next)

    return middleware


async def buffer_neutral_source_body(request: Request):
    """Bound actual uncompressed bytes before FastAPI materializes its typed body."""
    if request.headers.get("content-encoding", "identity") != "identity":
        return JSONResponse(status_code=415, content={"detail": "source_body_encoding_unsupported"})
    request.state.neutral_source_received_at = datetime.now(UTC)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1048576:
            return JSONResponse(status_code=413, content={"detail": "source_body_byte_budget"})
        body.extend(chunk)
    # Starlette's cached body is replayed by BaseHTTPMiddleware to the typed route.
    request._body = bytes(body)
    try:
        closed_source_json(request._body.decode("utf-8"))
    except ValueError:
        return JSONResponse(status_code=422, content={"detail": "SOURCE_CLOSED_JSON_REQUIRED"})
    request.state.neutral_source_closed_json = True
    return None
