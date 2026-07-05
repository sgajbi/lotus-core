import pytest
from fastapi import FastAPI

from src.services.calculators.cashflow_calculator_service.app.web import (
    app as cashflow_calculator_service_app,
)
from src.services.calculators.cost_calculator_service.app.web import (
    app as cost_calculator_service_app,
)
from src.services.calculators.position_calculator.app.web import (
    app as position_calculator_service_app,
)
from src.services.calculators.position_valuation_calculator.app.web import (
    app as position_valuation_calculator_app,
)
from src.services.event_replay_service.app.main import app as event_replay_service_app
from src.services.financial_reconciliation_service.app.main import (
    app as financial_reconciliation_service_app,
)
from src.services.ingestion_service.app.main import app as ingestion_service_app
from src.services.persistence_service.app.web import app as persistence_service_app
from src.services.pipeline_orchestrator_service.app.web import (
    app as pipeline_orchestrator_service_app,
)
from src.services.portfolio_aggregation_service.app.web import (
    app as portfolio_aggregation_service_app,
)
from src.services.query_control_plane_service.app.main import (
    app as query_control_plane_service_app,
)
from src.services.query_service.app.main import app as query_service_app
from src.services.timeseries_generator_service.app.web import (
    app as timeseries_generator_service_app,
)
from src.services.valuation_orchestrator_service.app.web import (
    app as valuation_orchestrator_service_app,
)
from tests.test_support.http_middleware_contract import (
    assert_standard_http_middleware_contract,
)

SERVICE_APPS: tuple[tuple[str, FastAPI], ...] = (
    ("cashflow_calculator_service_web", cashflow_calculator_service_app),
    ("cost_calculator_service_web", cost_calculator_service_app),
    ("position_calculator_service_web", position_calculator_service_app),
    ("position_valuation_calculator_service_web", position_valuation_calculator_app),
    ("event_replay_service", event_replay_service_app),
    ("financial_reconciliation_service", financial_reconciliation_service_app),
    ("ingestion_service", ingestion_service_app),
    ("persistence_service_web", persistence_service_app),
    ("pipeline_orchestrator_service_web", pipeline_orchestrator_service_app),
    ("portfolio_aggregation_service_web", portfolio_aggregation_service_app),
    ("query_control_plane_service", query_control_plane_service_app),
    ("query_service", query_service_app),
    ("timeseries_generator_service_web", timeseries_generator_service_app),
    ("valuation_orchestrator_service_web", valuation_orchestrator_service_app),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("service_name", "app"), SERVICE_APPS)
async def test_service_app_entrypoint_uses_standard_http_middleware_chain(
    service_name: str,
    app: FastAPI,
) -> None:
    await assert_standard_http_middleware_contract(
        app=app,
        service_name=service_name,
        correlation_id=f"{service_name}-corr",
    )
