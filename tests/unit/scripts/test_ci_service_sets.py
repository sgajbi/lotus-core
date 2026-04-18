from scripts.ci_service_sets import DOCKER_SMOKE_SERVICES


def test_docker_smoke_services_include_buy_state_calculators() -> None:
    assert "cost_calculator_service" in DOCKER_SMOKE_SERVICES
    assert "cashflow_calculator_service" in DOCKER_SMOKE_SERVICES
