import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.logging_utils import (
    correlation_id_var,
    generate_correlation_id,
    normalize_lineage_value,
    request_id_var,
    trace_id_var,
)
from portfolio_common.monitoring import HTTP_REQUEST_LATENCY_SECONDS, HTTP_REQUESTS_TOTAL
from portfolio_common.openapi_enrichment import enrich_openapi_schema


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
        metrics_response = (
            schema.get("paths", {})
            .get("/metrics", {})
            .get("get", {})
            .get("responses", {})
            .get("200")
        )
        if isinstance(metrics_response, dict):
            metrics_response["content"] = {"text/plain": {"schema": {"type": "string"}}}
        schema = enrich_openapi_schema(schema, service_name=service_name)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi


def configure_standard_http_app(
    app: FastAPI,
    *,
    service_name: str,
    service_prefix: str,
    logger: logging.Logger,
    id_generator=generate_correlation_id,
) -> None:
    Instrumentator().instrument(app).expose(app)
    logger.info("Prometheus metrics exposed at /metrics")

    configure_standard_openapi(app, service_name=service_name)

    @app.middleware("http")
    async def add_correlation_id_middleware(request: Request, call_next):
        correlation_id = normalize_lineage_value(
            request.headers.get("X-Correlation-Id") or request.headers.get("X-Correlation-ID")
        )
        request_id = normalize_lineage_value(request.headers.get("X-Request-Id"))
        trace_id = normalize_lineage_value(request.headers.get("X-Trace-Id"))
        if not correlation_id:
            correlation_id = id_generator(service_prefix)
        if not request_id:
            request_id = id_generator("REQ")
        if not trace_id:
            trace_id = uuid4().hex

        correlation_token = correlation_id_var.set(correlation_id)
        request_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        response.headers["traceparent"] = f"00-{trace_id}-0000000000000001-01"
        correlation_id_var.reset(correlation_token)
        request_id_var.reset(request_token)
        trace_id_var.reset(trace_token)
        return response

    @app.middleware("http")
    async def emit_http_observability(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        labels = {
            "service": service_name,
            "method": request.method,
            "path": request.url.path,
        }
        HTTP_REQUEST_LATENCY_SECONDS.labels(**labels).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(status=str(response.status_code), **labels).inc()

        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
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
