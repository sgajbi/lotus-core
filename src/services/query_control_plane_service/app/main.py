import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.http_app_bootstrap import configure_standard_http_app, include_routers
from portfolio_common.logging_utils import generate_correlation_id, setup_logging

from .enterprise_readiness import (
    build_enterprise_audit_middleware,
    validate_enterprise_runtime_config,
)
from .routers import (
    advisory_simulation,
    analytics_inputs,
    capabilities,
    integration,
    operations,
    simulation,
)

SERVICE_PREFIX = "QCP"
SERVICE_NAME = "query_control_plane_service"
setup_logging()
logger = logging.getLogger(__name__)
validate_enterprise_runtime_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Query Control Plane Service starting up...")
    yield
    logger.info(
        "Query Control Plane Service shutting down. Waiting for in-flight requests to complete..."
    )
    logger.info("Query Control Plane Service has shut down gracefully.")


app = FastAPI(
    title="Lotus Core Query Control Plane API",
    description=(
        "Lotus Core control-plane APIs for integration contracts, operational support, "
        "and simulation workflows. Core read-plane endpoints remain in query_service."
    ),
    version="0.2.0",
    contact={"name": "Lotus Platform Engineering"},
    lifespan=lifespan,
)
app.middleware("http")(build_enterprise_audit_middleware())
configure_standard_http_app(
    app,
    service_name=SERVICE_NAME,
    service_prefix=SERVICE_PREFIX,
    logger=logger,
    id_generator=lambda prefix: generate_correlation_id(prefix),
)

health_router = create_health_router("db")
include_routers(
    app,
    health_router,
    operations.router,
    integration.router,
    advisory_simulation.router,
    analytics_inputs.router,
    capabilities.router,
    simulation.router,
)
