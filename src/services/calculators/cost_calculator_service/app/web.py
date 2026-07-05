# services/calculators/cost_calculator_service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "cost_calculator_service_web"

app = create_standard_health_app(
    title="Cost Calculator - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="CST",
    dependencies=("db", "kafka", "worker_runtime"),
)
