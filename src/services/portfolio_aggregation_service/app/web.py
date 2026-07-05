# services/timeseries-generator-service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "portfolio_aggregation_service_web"

app = create_standard_health_app(
    title="Portfolio Aggregation Service - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="AGG",
    dependencies=("db", "kafka", "worker_runtime"),
)
