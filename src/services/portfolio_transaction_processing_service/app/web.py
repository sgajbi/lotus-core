from portfolio_common.http_app_bootstrap import create_standard_health_app

WORKER_READINESS_SERVICE_NAME = "portfolio_transaction_processing_service_web"

app = create_standard_health_app(
    title="Portfolio Transaction Processing - Health",
    service_name=WORKER_READINESS_SERVICE_NAME,
    service_prefix="PTP",
    dependencies=("db", "kafka", "worker_runtime"),
)
