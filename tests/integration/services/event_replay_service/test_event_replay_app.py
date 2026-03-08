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


async def test_openapi_includes_replay_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    retry_operation = schema["paths"]["/ingestion/jobs/{job_id}/retry"]["post"]
    retry_examples = retry_operation["requestBody"]["content"]["application/json"]["examples"]
    retry_response_example = retry_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert "partial_dry_run" in retry_examples
    assert retry_examples["partial_dry_run"]["value"]["dry_run"] is True
    assert retry_response_example["job_id"] == "job_01J5S0J6D3BAVMK2E1V0WQ7MCC"

    replay_operation = schema["paths"]["/ingestion/dlq/consumer-events/{event_id}/replay"]["post"]
    replay_examples = replay_operation["requestBody"]["content"]["application/json"]["examples"]
    replay_response_example = replay_operation["responses"]["200"]["content"][
        "application/json"
    ]["example"]
    assert "replay_now" in replay_examples
    assert replay_response_example["replay_status"] == "replayed"

    ops_control_example = schema["paths"]["/ingestion/ops/control"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["example"]
    assert ops_control_example["mode"] == "paused"


async def test_openapi_excludes_write_ingress_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingest/transactions" not in paths
    assert "/ingest/portfolios" not in paths
    assert "/ingest/instruments" not in paths
