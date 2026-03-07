# services/calculators/position_valuation_calculator/app/web.py
from fastapi import FastAPI
from portfolio_common.health import create_health_router

app = FastAPI(title="Position Valuation Calculator - Health")

# Create and include the standardized health router.
# This service depends on the database.
health_router = create_health_router("db")
app.include_router(health_router)
