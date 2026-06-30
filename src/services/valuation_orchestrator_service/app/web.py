# services/calculators/position_valuation_calculator/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Valuation Orchestrator Service - Health",
    service_name="valuation_orchestrator_service_web",
    service_prefix="VAL",
    dependencies=("db",),
)
