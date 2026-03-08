from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.event_replay_service.app.main import app, lifespan

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
        "src.services.event_replay_service.app.main.generate_correlation_id",
        return_value="ERP-abc",
    ):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "ERP-abc"


async def test_lifespan_logs_startup_and_shutdown():
    with patch("src.services.event_replay_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Event Replay Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Event Replay Service has shut down gracefully." in logged_messages


async def test_openapi_contains_replay_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingestion/jobs" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    assert "/ingestion/dlq/consumer-events/{event_id}/replay" in paths
    assert "/ingestion/health/policy" in paths
    assert "/ingestion/audit/replays" in paths


async def test_openapi_excludes_write_ingress_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingest/transactions" not in paths
    assert "/ingest/portfolios" not in paths
    assert "/ingest/instruments" not in paths
