# services/timeseries-generator-service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Portfolio Aggregation Service - Health",
    service_name="portfolio_aggregation_service_web",
    service_prefix="AGG",
    dependencies=("db",),
)
