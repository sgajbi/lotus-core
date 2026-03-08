import httpx
import pytest
import pytest_asyncio

from src.services.ingestion_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_openapi_declares_metrics_as_text_plain(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    metrics_content = response.json()["paths"]["/metrics"]["get"]["responses"]["200"]["content"]
    assert "text/plain" in metrics_content
    assert "application/json" not in metrics_content


async def test_metrics_include_http_series_samples(async_test_client):
    traffic_response = await async_test_client.get("/openapi.json")
    assert traffic_response.status_code == 200

    metrics_response = await async_test_client.get("/metrics")
    assert metrics_response.status_code == 200

    metrics_text = metrics_response.text
    assert "http_requests_total{" in metrics_text
    assert "http_request_latency_seconds_count{" in metrics_text


async def test_openapi_declares_upload_400_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "400" in paths["/ingest/uploads/preview"]["post"]["responses"]
    assert "400" in paths["/ingest/uploads/commit"]["post"]["responses"]
    assert "410" in paths["/ingest/uploads/preview"]["post"]["responses"]
    assert "410" in paths["/ingest/uploads/commit"]["post"]["responses"]
    assert "410" in paths["/ingest/portfolio-bundle"]["post"]["responses"]


async def test_openapi_excludes_event_replay_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/ingestion/jobs" not in paths
    assert "/ingestion/dlq/consumer-events" not in paths
    assert "/ingestion/health/policy" not in paths
