from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Pipeline Orchestrator Service",
    service_name="pipeline_orchestrator_service_web",
    service_prefix="PIP",
    dependencies=("db",),
)
