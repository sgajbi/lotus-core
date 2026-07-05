# services/calculators/position_valuation_calculator/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "valuation_orchestrator_service_web"

app = create_standard_health_app(
    title="Valuation Orchestrator Service - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="VAL",
    dependencies=("db", "kafka", "worker_runtime"),
)
