# services/persistence_service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Persistence Service - Health",
    service_name="persistence_service_web",
    service_prefix="PST",
    dependencies=("db", "kafka"),
    description="Provides health and readiness probes for the Persistence Service.",
    version="1.0.0",
)
