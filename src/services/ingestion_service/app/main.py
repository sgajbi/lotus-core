# services/ingestion_service/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.http_app_bootstrap import configure_standard_http_app, include_routers
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.logging_utils import generate_correlation_id, setup_logging

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

SERVICE_PREFIX = "ING"
SERVICE_NAME = "ingestion_service"
setup_logging()
logger = logging.getLogger(__name__)

app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception as exc:
        logger.critical("FATAL: Could not initialize Kafka producer on startup.", exc_info=True)
        app_state["kafka_producer"] = None
        raise RuntimeError(
            "ingestion_service failed startup because Kafka producer initialization failed"
        ) from exc

    yield

    logger.info("Ingestion Service shutting down...")
    producer = app_state.get("kafka_producer")
    if producer:
        logger.info("Flushing Kafka producer to send all buffered messages...")
        producer.flush(timeout=5)
    logger.info("Kafka producer flushed successfully.")
    logger.info("Ingestion Service has shut down gracefully.")


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
configure_standard_http_app(
    app,
    service_name=SERVICE_NAME,
    service_prefix=SERVICE_PREFIX,
    logger=logger,
    id_generator=lambda prefix: generate_correlation_id(prefix),
)

health_router = create_health_router("kafka")
include_routers(
    app,
    health_router,
    portfolios.router,
    transactions.router,
    instruments.router,
    market_prices.router,
    fx_rates.router,
    business_dates.router,
    reprocessing.router,
    portfolio_bundle.router,
    uploads.router,
    reference_data.router,
)
