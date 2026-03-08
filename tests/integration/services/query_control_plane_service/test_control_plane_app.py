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
