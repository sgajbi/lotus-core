import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.http_app_bootstrap import configure_standard_http_app, include_routers
from portfolio_common.logging_utils import generate_correlation_id, setup_logging

from .routers import ingestion_operations

SERVICE_PREFIX = "ERP"
SERVICE_NAME = "event_replay_service"
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Event Replay Service starting up...")
    yield
    logger.info("Event Replay Service shutting down. Waiting for in-flight requests to complete...")
    logger.info("Event Replay Service has shut down gracefully.")


app = FastAPI(
    title="Lotus Core Event Replay API",
    description=(
        "Lotus Core replay and remediation control-plane APIs for ingestion jobs, "
        "RFC-065 operational diagnostics, DLQ recovery, and replay governance. "
        "Canonical write-ingress endpoints remain in ingestion_service."
    ),
    version="0.1.0",
    contact={"name": "Lotus Platform Engineering"},
    lifespan=lifespan,
)
configure_standard_http_app(
    app,
    service_name=SERVICE_NAME,
    service_prefix=SERVICE_PREFIX,
    logger=logger,
    id_generator=lambda prefix: generate_correlation_id(prefix),
)

health_router = create_health_router("db", "kafka")
include_routers(app, health_router, ingestion_operations.router)
