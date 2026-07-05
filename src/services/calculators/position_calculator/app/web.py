# services/calculators/position_calculator/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "position_calculator_service_web"

app = create_standard_health_app(
    title="Position Calculator - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="POS",
    dependencies=("db", "kafka", "worker_runtime"),
)
