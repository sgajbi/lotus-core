# services/calculators/position_calculator/app/web.py
from portfolio_common.http_app_bootstrap import create_standard_health_app

app = create_standard_health_app(
    title="Position Calculator - Health",
    service_name="position_calculator_service_web",
    service_prefix="POS",
    dependencies=("db",),
)
