# services/ingestion_service/app/main.py
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from .routers import (
    business_dates,
    fx_rates,
    instruments,
    market_prices,
    portfolio_bundle,
    portfolios,
    reference_data,
    reprocessing,
    transactions,
    uploads,
)
from fastapi import FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from portfolio_common.health import create_health_router
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.logging_utils import (
    correlation_id_var,
    generate_correlation_id,
    request_id_var,
    setup_logging,
    trace_id_var,
)
from portfolio_common.monitoring import HTTP_REQUEST_LATENCY_SECONDS, HTTP_REQUESTS_TOTAL
from portfolio_common.openapi_enrichment import enrich_openapi_schema
from prometheus_fastapi_instrumentator import Instrumentator

SERVICE_PREFIX = "ING"
SERVICE_NAME = "ingestion_service"
setup_logging()
logger = logging.getLogger(__name__)

# Application state to hold shared resources like the producer
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events for graceful operation.
    """
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception:
        logger.critical("FATAL: Could not initialize Kafka producer on startup.", exc_info=True)
        app_state["kafka_producer"] = None

    yield

    logger.info("Ingestion Service shutting down...")
    producer = app_state.get("kafka_producer")
    if producer:
        logger.info("Flushing Kafka producer to send all buffered messages...")
        producer.flush(timeout=5)
    logger.info("Kafka producer flushed successfully.")
    logger.info("Ingestion Service has shut down gracefully.")


# Main FastAPI app instance
app = FastAPI(
    title="Lotus Core Ingestion API",
    description=(
        "Lotus Core Ingestion API for onboarding canonical financial data into Lotus Core. "
        "Supports Lotus-standard ingestion contracts for portfolios, instruments, transactions, "
        "market prices, FX rates, business dates, and controlled reprocessing workflows. "
        "Replay, DLQ remediation, and ingestion operations diagnostics are hosted by "
        "event_replay_service."
    ),
    version="0.5.0",
    contact={"name": "Lotus Platform Engineering"},
    lifespan=lifespan,
)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")


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
        schema.get("paths", {}).get("/metrics", {}).get("get", {}).get("responses", {}).get("200")
    )
    if isinstance(metrics_response, dict):
        metrics_response["content"] = {"text/plain": {"schema": {"type": "string"}}}
    schema = enrich_openapi_schema(schema, service_name=SERVICE_NAME)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# Correlation ID Middleware
@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or request.headers.get(
        "X-Correlation-ID"
    )
    if not correlation_id:
        correlation_id = generate_correlation_id(SERVICE_PREFIX)
    request_id = request.headers.get("X-Request-Id") or generate_correlation_id("REQ")
    trace_id = request.headers.get("X-Trace-Id") or uuid4().hex

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
        "service": SERVICE_NAME,
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


# Global Exception Handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exceptions and returns a standardized 500 error response.
    """
    correlation_id = (
        request.headers.get("X-Correlation-Id")
        or request.headers.get("X-Correlation-ID")
        or correlation_id_var.get()
    )
    if correlation_id == "<not-set>":
        correlation_id = generate_correlation_id(SERVICE_PREFIX)
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


# Create and include the standardized health router.
# This service depends on Kafka.
health_router = create_health_router("kafka")
app.include_router(health_router)

# Include the API routers
app.include_router(portfolios.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(market_prices.router)
app.include_router(fx_rates.router)
app.include_router(business_dates.router)
app.include_router(reprocessing.router)
app.include_router(portfolio_bundle.router)
app.include_router(uploads.router)
app.include_router(reference_data.router)
