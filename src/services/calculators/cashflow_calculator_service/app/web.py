# services/calculators/cashflow_calculator_service/app/web.py
from fastapi import FastAPI
from portfolio_common.health import create_health_router

app = FastAPI(title="Cashflow Calculator - Health")

# Create and include the standardized health router.
# This service depends on the database.
health_router = create_health_router("db")
app.include_router(health_router)
