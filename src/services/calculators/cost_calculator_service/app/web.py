# services/calculators/cost_calculator_service/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Cost Calculator - Health",
    service_name="cost_calculator_service_web",
    service_prefix="CST",
    dependencies=("db",),
)
