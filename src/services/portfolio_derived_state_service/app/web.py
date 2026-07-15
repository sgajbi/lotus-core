"""Expose health, readiness, metrics, and build metadata for derived-state workers."""

from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "portfolio_derived_state_service_web"

app = create_standard_health_app(
    title="Portfolio Derived State Service - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="PDS",
    dependencies=("db", "kafka", "worker_runtime"),
)
