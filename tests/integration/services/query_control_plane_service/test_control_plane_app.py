from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.query_control_plane_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_middleware_preserves_incoming_correlation_id(async_test_client):
    response = await async_test_client.get(
        "/openapi.json", headers={"X-Correlation-ID": "corr-123"}
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"


async def test_middleware_generates_correlation_id_when_missing(async_test_client):
    with patch(
        "src.services.query_control_plane_service.app.main.generate_correlation_id",
        return_value="QCP-abc",
    ):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QCP-abc"


async def test_lifespan_logs_startup_and_shutdown():
    with patch("src.services.query_control_plane_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Query Control Plane Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Query Control Plane Service has shut down gracefully." in logged_messages


async def test_openapi_contains_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/integration/capabilities" in paths
    assert "/integration/portfolios/{portfolio_id}/core-snapshot" in paths
    assert "/support/portfolios/{portfolio_id}/overview" in paths
    assert "/simulation-sessions/{session_id}" in paths
    assert "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries" in paths


async def test_openapi_excludes_core_read_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/portfolios/{portfolio_id}" not in paths
    assert "/portfolios/{portfolio_id}/positions" not in paths
    assert "/portfolios/{portfolio_id}/transactions" not in paths


async def test_openapi_describes_operations_support_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    overview = schema["paths"]["/support/portfolios/{portfolio_id}/overview"]["get"]
    calculator_slos = schema["paths"]["/support/portfolios/{portfolio_id}/calculator-slos"]["get"]
    lineage = schema["paths"]["/lineage/portfolios/{portfolio_id}/securities/{security_id}"]["get"]

    overview_portfolio = next(
        parameter for parameter in overview["parameters"] if parameter["name"] == "portfolio_id"
    )
    assert overview_portfolio["description"] == "Portfolio identifier."

    stale_threshold = next(
        parameter
        for parameter in calculator_slos["parameters"]
        if parameter["name"] == "stale_threshold_minutes"
    )
    assert stale_threshold["description"].startswith("Threshold in minutes")

    not_found_example = overview["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found_example["detail"] == "Portfolio with id PORT-OPS-001 not found"

    lineage_not_found = lineage["responses"]["404"]["content"]["application/json"]["example"]
    assert lineage_not_found["detail"] == (
        "Lineage for portfolio PORT-OPS-001 and security SEC-US-IBM not found"
    )


async def test_openapi_describes_simulation_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    get_session = schema["paths"]["/simulation-sessions/{session_id}"]["get"]
    delete_change = schema["paths"]["/simulation-sessions/{session_id}/changes/{change_id}"][
        "delete"
    ]
    create_session = schema["components"]["schemas"]["SimulationSessionCreateRequest"]

    session_param = next(
        parameter for parameter in get_session["parameters"] if parameter["name"] == "session_id"
    )
    assert session_param["description"] == "Simulation session identifier."

    not_found = get_session["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Simulation session SIM-20260310-0001 not found"

    change_id_param = next(
        parameter for parameter in delete_change["parameters"] if parameter["name"] == "change_id"
    )
    assert change_id_param["description"] == "Simulation change identifier."

    portfolio_id = create_session["properties"]["portfolio_id"]
    assert portfolio_id["description"] == "Portfolio identifier for the simulated scenario."


async def test_openapi_describes_analytics_input_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    portfolio_inputs = schema["paths"][
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries"
    ]["post"]
    export_result = schema["paths"][
        "/integration/exports/analytics-timeseries/jobs/{job_id}/result"
    ]["get"]

    portfolio_param = next(
        parameter
        for parameter in portfolio_inputs["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == (
        "Portfolio identifier for the requested analytics input contract."
    )

    invalid_request = portfolio_inputs["responses"]["400"]["content"]["application/json"]["example"]
    assert invalid_request["detail"] == "Either window or period must be provided."

    job_id_param = next(
        parameter for parameter in export_result["parameters"] if parameter["name"] == "job_id"
    )
    assert job_id_param["description"] == "Durable analytics export job identifier."

    incomplete_export = export_result["responses"]["422"]["content"]["application/json"]["example"]
    assert incomplete_export["detail"] == "Analytics export job JOB-AN-0001 is not complete."
