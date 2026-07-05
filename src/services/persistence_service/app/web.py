# services/persistence_service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "persistence_service_web"

app = create_standard_health_app(
    title="Persistence Service - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="PST",
    dependencies=("db", "kafka", "worker_runtime"),
    description="Provides health and readiness probes for the Persistence Service.",
    version="1.0.0",
)
