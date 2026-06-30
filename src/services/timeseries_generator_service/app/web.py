# services/timeseries-generator-service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Timeseries Generator - Health",
    service_name="timeseries_generator_service_web",
    service_prefix="TSG",
    dependencies=("db",),
)
