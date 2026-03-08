# services/persistence_service/app/web.py
from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.openapi_enrichment import attach_enriched_openapi

from .monitoring import setup_metrics

app = FastAPI(
    title="Persistence Service - Health",
    description="Provides health and readiness probes for the Persistence Service.",
    version="1.0.0",
)
attach_enriched_openapi(app, service_name="persistence_service_web")

# Setup and expose the /metrics endpoint
setup_metrics(app)

# Create and include the standardized health router.
# This service depends on both the database and Kafka.
health_router = create_health_router("db", "kafka")
app.include_router(health_router)
