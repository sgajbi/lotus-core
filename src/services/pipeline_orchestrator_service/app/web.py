from fastapi import FastAPI
from portfolio_common.health import create_health_router
from portfolio_common.openapi_enrichment import attach_enriched_openapi

app = FastAPI(title="Pipeline Orchestrator Service")
attach_enriched_openapi(app, service_name="pipeline_orchestrator_service_web")
health_router = create_health_router("db")
app.include_router(health_router)
