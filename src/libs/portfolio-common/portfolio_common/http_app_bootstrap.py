import logging
import time
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any, Sequence
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware

from portfolio_common.health import create_health_router
from portfolio_common.logging_utils import (
    correlation_id_var,
    generate_correlation_id,
    normalize_lineage_value,
    normalize_trace_id,
    normalize_traceparent,
    request_id_var,
    trace_id_from_traceparent,
    trace_id_var,
    traceparent_from_trace_id,
    traceparent_var,
)
from portfolio_common.metrics_settings import load_metrics_runtime_settings
from portfolio_common.monitoring import HTTP_REQUEST_LATENCY_SECONDS, HTTP_REQUESTS_TOTAL
from portfolio_common.openapi_enrichment import enrich_openapi_schema
from portfolio_common.runtime_settings import env_str

UNMATCHED_ROUTE_TEMPLATE = "<unmatched>"
METRICS_INTERNAL_OPEN_MODE = "internal_open"
METRICS_PROTECTED_SCRAPE_MODE = "protected_scrape"
_METRICS_POLICY_CONFIGURED_STATE_KEY = "lotus_metrics_access_policy_configured"
_SECURITY_HEADERS_CONFIGURED_STATE_KEY = "lotus_secure_response_headers_configured"
_CORS_POLICY_CONFIGURED_STATE_KEY = "lotus_cors_policy_configured"
HTTP_CORS_ALLOW_ORIGINS_ENV = "LOTUS_HTTP_CORS_ALLOW_ORIGINS"

SECURE_RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@dataclass(frozen=True)
class MetricsAccessPolicy:
    mode: str
    token: str | None = None

    @property
    def protected(self) -> bool:
        return self.mode == METRICS_PROTECTED_SCRAPE_MODE


def resolve_metrics_access_policy(
    metrics_access_token: str | None = None,
) -> MetricsAccessPolicy:
    token = normalize_lineage_value(metrics_access_token)
    if token is None:
        token = load_metrics_runtime_settings().metrics_access_token
    if token:
        return MetricsAccessPolicy(mode=METRICS_PROTECTED_SCRAPE_MODE, token=token)
    return MetricsAccessPolicy(mode=METRICS_INTERNAL_OPEN_MODE)


def _metrics_request_allowed(request: Request, policy: MetricsAccessPolicy) -> bool:
    if not policy.protected:
        return True
    configured_token = policy.token
    if not configured_token:
        return False
    authorization = request.headers.get("Authorization", "")
    bearer_prefix = "Bearer "
    if not authorization.startswith(bearer_prefix):
        return False
    supplied_token = authorization[len(bearer_prefix) :].strip()
    return bool(supplied_token) and compare_digest(supplied_token, configured_token)


def _metrics_forbidden_response(policy: MetricsAccessPolicy) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "detail": {
                "code": "METRICS_ACCESS_DENIED",
                "message": "Metrics endpoint access is restricted to authorized scrapers.",
                "metrics_access_mode": policy.mode,
            }
        },
    )


def configure_metrics_access_policy(
    app: FastAPI,
    *,
    metrics_access_policy: MetricsAccessPolicy,
) -> None:
    if getattr(app.state, _METRICS_POLICY_CONFIGURED_STATE_KEY, False):
        return
    setattr(app.state, _METRICS_POLICY_CONFIGURED_STATE_KEY, True)

    @app.middleware("http")
    async def enforce_metrics_access_policy(request: Request, call_next):
        if request.url.path == "/metrics" and not _metrics_request_allowed(
            request,
            metrics_access_policy,
        ):
            return _metrics_forbidden_response(metrics_access_policy)
        return await call_next(request)


def _normalized_csv_values(raw_value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def resolve_cors_allow_origins(
    cors_allow_origins: Sequence[str] | None = None,
) -> tuple[str, ...]:
    if cors_allow_origins is not None:
        return tuple(origin.strip() for origin in cors_allow_origins if origin.strip())
    return _normalized_csv_values(env_str(HTTP_CORS_ALLOW_ORIGINS_ENV, ""))


def configure_cors_policy(
    app: FastAPI,
    *,
    cors_allow_origins: Sequence[str] | None = None,
) -> tuple[str, ...]:
    if getattr(app.state, _CORS_POLICY_CONFIGURED_STATE_KEY, False):
        return tuple(getattr(app.state, "lotus_cors_allow_origins", ()))
    origins = resolve_cors_allow_origins(cors_allow_origins)
    setattr(app.state, _CORS_POLICY_CONFIGURED_STATE_KEY, True)
    setattr(app.state, "lotus_cors_allow_origins", origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Actor-Id",
            "X-Correlation-ID",
            "X-Correlation-Id",
            "X-Request-Id",
            "X-Role",
            "X-Service-Identity",
            "X-Tenant-Id",
            "traceparent",
        ],
    )
    return origins


def configure_secure_response_headers(app: FastAPI) -> None:
    if getattr(app.state, _SECURITY_HEADERS_CONFIGURED_STATE_KEY, False):
        return
    setattr(app.state, _SECURITY_HEADERS_CONFIGURED_STATE_KEY, True)

    @app.middleware("http")
    async def add_secure_response_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURE_RESPONSE_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


def http_metric_path_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return UNMATCHED_ROUTE_TEMPLATE


def configure_standard_openapi(app: FastAPI, *, service_name: str) -> None:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _ensure_metrics_openapi_contract(schema)
        schema = enrich_openapi_schema(schema, service_name=service_name)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi


def _ensure_metrics_openapi_contract(schema: dict[str, Any]) -> None:
    metrics_operation = schema.get("paths", {}).get("/metrics", {}).get("get")
    if not isinstance(metrics_operation, dict):
        return
    metrics_operation["summary"] = "Prometheus metrics scrape endpoint"
    metrics_operation["description"] = (
        "Operational Prometheus scrape endpoint. This is not a public business API; access is "
        "governed by the shared metrics access policy and should be reachable only by authorized "
        "scrapers or a private metrics network."
    )
    metrics_operation["tags"] = ["Monitoring"]
    responses = metrics_operation.setdefault("responses", {})
    response_200 = responses.setdefault("200", {"description": "Prometheus metrics payload."})
    if isinstance(response_200, dict):
        response_200["content"] = {"text/plain": {"schema": {"type": "string"}}}
    responses.setdefault(
        "403",
        {
            "description": "Metrics scrape was denied by the shared metrics access policy.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "METRICS_ACCESS_DENIED",
                            "message": (
                                "Metrics endpoint access is restricted to authorized scrapers."
                            ),
                            "metrics_access_mode": METRICS_PROTECTED_SCRAPE_MODE,
                        }
                    }
                }
            },
        },
    )


def configure_standard_http_app(
    app: FastAPI,
    *,
    service_name: str,
    service_prefix: str,
    logger: logging.Logger,
    id_generator=generate_correlation_id,
    metrics_access_token: str | None = None,
    cors_allow_origins: Sequence[str] | None = None,
) -> None:
    metrics_access_policy = resolve_metrics_access_policy(metrics_access_token)
    configured_cors_origins = configure_cors_policy(
        app,
        cors_allow_origins=cors_allow_origins,
    )
    configure_secure_response_headers(app)
    Instrumentator().instrument(app).expose(app)
    logger.info(
        "Prometheus metrics exposed at /metrics",
        extra={"metrics_access_mode": metrics_access_policy.mode},
    )
    logger.info(
        "HTTP CORS policy configured.",
        extra={
            "cors_allow_origin_count": len(configured_cors_origins),
            "cors_policy_mode": "explicit_origins" if configured_cors_origins else "deny_browser",
        },
    )

    configure_standard_openapi(app, service_name=service_name)
    configure_metrics_access_policy(app, metrics_access_policy=metrics_access_policy)

    @app.middleware("http")
    async def add_correlation_id_middleware(request: Request, call_next):
        correlation_id = normalize_lineage_value(
            request.headers.get("X-Correlation-Id") or request.headers.get("X-Correlation-ID")
        )
        request_id = normalize_lineage_value(request.headers.get("X-Request-Id"))
        traceparent = normalize_traceparent(request.headers.get("traceparent"))
        trace_id = trace_id_from_traceparent(traceparent) or normalize_trace_id(
            request.headers.get("X-Trace-Id")
        )
        if not correlation_id:
            correlation_id = id_generator(service_prefix)
        if not request_id:
            request_id = id_generator("REQ")
        if not trace_id:
            trace_id = uuid4().hex
        if not traceparent:
            traceparent = traceparent_from_trace_id(trace_id)
        if not traceparent:
            trace_id = uuid4().hex
            traceparent = traceparent_from_trace_id(trace_id)
        if not traceparent:  # pragma: no cover - uuid4-generated trace IDs should be valid.
            raise RuntimeError("failed to generate W3C traceparent context")

        correlation_token = correlation_id_var.set(correlation_id)
        request_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)
        traceparent_token = traceparent_var.set(traceparent)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        response.headers["traceparent"] = traceparent
        correlation_id_var.reset(correlation_token)
        request_id_var.reset(request_token)
        trace_id_var.reset(trace_token)
        traceparent_var.reset(traceparent_token)
        return response

    @app.middleware("http")
    async def emit_http_observability(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route_template = http_metric_path_template(request)

        labels = {
            "service": service_name,
            "method": request.method,
            "endpoint_template": route_template,
        }
        HTTP_REQUEST_LATENCY_SECONDS.labels(**labels).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(status=str(response.status_code), **labels).inc()

        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "route_template": route_template,
                "status_code": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            },
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        correlation_id = (
            request.headers.get("X-Correlation-Id")
            or request.headers.get("X-Correlation-ID")
            or correlation_id_var.get()
        )
        correlation_id = normalize_lineage_value(correlation_id)
        if correlation_id is None:
            correlation_id = id_generator(service_prefix)
        logger.critical(
            f"Unhandled exception for request {request.method} {request.url}",
            exc_info=exc,
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please contact support.",
                "correlation_id": correlation_id,
            },
        )


def include_routers(app: FastAPI, *routers: Any) -> None:
    for router in routers:
        app.include_router(router)


def create_standard_health_app(
    *,
    title: str,
    service_name: str,
    service_prefix: str,
    dependencies: tuple[str, ...],
    description: str | None = None,
    version: str = "1.0.0",
    logger: logging.Logger | None = None,
    id_generator=generate_correlation_id,
    metrics_access_token: str | None = None,
    cors_allow_origins: Sequence[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title=title,
        description=description,
        version=version,
    )
    app_logger = logger or logging.getLogger(service_name)
    configure_standard_http_app(
        app,
        service_name=service_name,
        service_prefix=service_prefix,
        logger=app_logger,
        id_generator=id_generator,
        metrics_access_token=metrics_access_token,
        cors_allow_origins=cors_allow_origins,
    )
    include_routers(app, create_health_router(*dependencies, service_name=service_name))
    return app
