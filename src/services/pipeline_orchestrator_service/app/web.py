from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "pipeline_orchestrator_service_web"

app = create_standard_health_app(
    title="Pipeline Orchestrator Service",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="PIP",
    dependencies=("db", "kafka", "worker_runtime"),
)
