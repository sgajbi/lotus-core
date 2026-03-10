import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.http_app_bootstrap import configure_standard_http_app, include_routers
from portfolio_common.logging_utils import generate_correlation_id, setup_logging

from .routers import router as reconciliation_router

SERVICE_PREFIX = "FRC"
SERVICE_NAME = "financial_reconciliation_service"
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Financial Reconciliation Service starting up...")
    yield
    logger.info(
        "Financial Reconciliation Service shutting down. "
        "Waiting for in-flight requests to complete..."
    )
    logger.info("Financial Reconciliation Service has shut down gracefully.")


app = FastAPI(
    title="Lotus Core Financial Reconciliation API",
    description=(
        "Lotus Core independent financial controls for transaction-cashflow completeness, "
        "position-valuation consistency, and timeseries integrity."
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

health_router = create_health_router("db")
include_routers(app, health_router, reconciliation_router)
