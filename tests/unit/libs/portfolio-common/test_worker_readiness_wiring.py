from pathlib import Path

WORKER_READINESS_WIRING = (
    (
        "cost_calculator_service_web",
        Path("src/services/calculators/cost_calculator_service/app/web.py"),
        Path("src/services/calculators/cost_calculator_service/app/consumer_manager.py"),
    ),
    (
        "position_calculator_service_web",
        Path("src/services/calculators/position_calculator/app/web.py"),
        Path("src/services/calculators/position_calculator/app/consumer_manager.py"),
    ),
    (
        "cashflow_calculator_service_web",
        Path("src/services/calculators/cashflow_calculator_service/app/web.py"),
        Path("src/services/calculators/cashflow_calculator_service/app/consumer_manager.py"),
    ),
    (
        "position_valuation_calculator_service_web",
        Path("src/services/calculators/position_valuation_calculator/app/web.py"),
        Path("src/services/calculators/position_valuation_calculator/app/consumer_manager.py"),
    ),
    (
        "pipeline_orchestrator_service_web",
        Path("src/services/pipeline_orchestrator_service/app/web.py"),
        Path("src/services/pipeline_orchestrator_service/app/consumer_manager.py"),
    ),
    (
        "portfolio_aggregation_service_web",
        Path("src/services/portfolio_aggregation_service/app/web.py"),
        Path("src/services/portfolio_aggregation_service/app/consumer_manager.py"),
    ),
    (
        "persistence_service_web",
        Path("src/services/persistence_service/app/web.py"),
        Path("src/services/persistence_service/app/consumer_manager.py"),
    ),
    (
        "timeseries_generator_service_web",
        Path("src/services/timeseries_generator_service/app/web.py"),
        Path("src/services/timeseries_generator_service/app/consumer_manager.py"),
    ),
    (
        "valuation_orchestrator_service_web",
        Path("src/services/valuation_orchestrator_service/app/web.py"),
        Path("src/services/valuation_orchestrator_service/app/consumer_manager.py"),
    ),
)


def test_worker_health_apps_and_managers_share_runtime_readiness_contract() -> None:
    for service_name, web_path, manager_path in WORKER_READINESS_WIRING:
        web_source = web_path.read_text(encoding="utf-8")
        manager_source = manager_path.read_text(encoding="utf-8")

        assert f'WORKER_READINESS_SERVICE_NAME = "{service_name}"' in web_source
        assert '"worker_runtime"' in web_source
        assert "from .web import WORKER_READINESS_SERVICE_NAME" in manager_source
        assert "from .web import app as web_app" in manager_source
        assert "readiness_service_name=WORKER_READINESS_SERVICE_NAME" in manager_source
