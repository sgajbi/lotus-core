# services/query-service/app/main.py
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
    buy_state,
    cash_accounts,
    cashflow_projection,
    fx_rates,
    instruments,
    lookups,
    portfolios,
    positions,
    prices,
    reporting,
    sell_state,
    transactions,
)

SERVICE_PREFIX = "QRY"
SERVICE_NAME = "query_service"
setup_logging()
logger = logging.getLogger(__name__)
validate_enterprise_runtime_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Query Service starting up...")
    yield
    logger.info("Query Service shutting down. Waiting for in-flight requests to complete...")
    logger.info("Query Service has shut down gracefully.")


app = FastAPI(
    title="Lotus Core Query API",
    description=(
        "Lotus Core Query API for portfolio and position data access. "
        "Provides Lotus-standard, API-first read models for portfolios, positions, "
        "transactions, PB/WM reporting, prices, instruments, and lookup workflows."
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
    portfolios.router,
    positions.router,
    cash_accounts.router,
    buy_state.router,
    sell_state.router,
    transactions.router,
    cashflow_projection.router,
    instruments.router,
    prices.router,
    fx_rates.router,
    lookups.router,
    reporting.router,
)
