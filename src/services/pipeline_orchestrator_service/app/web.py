from fastapi import FastAPI
from portfolio_common.health import create_health_router

app = FastAPI(title="Pipeline Orchestrator Service")
health_router = create_health_router("db")
app.include_router(health_router)
