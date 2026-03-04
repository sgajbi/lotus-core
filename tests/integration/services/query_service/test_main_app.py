from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app, lifespan

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
        "src.services.query_service.app.main.generate_correlation_id", return_value="QRY-abc"
    ):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QRY-abc"


async def test_global_exception_handler_returns_standard_payload(async_test_client):
    async def boom():
        raise RuntimeError("boom")

    app.add_api_route("/_test_raise", boom, methods=["GET"])
    try:
        response = await async_test_client.get(
            "/_test_raise", headers={"X-Correlation-ID": "corr-500"}
        )
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/_test_raise"
        ]

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    assert body["correlation_id"] == "corr-500"


async def test_lifespan_logs_startup_and_shutdown():
    with patch("src.services.query_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Query Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Query Service has shut down gracefully." in logged_messages


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


async def test_openapi_declares_simulation_error_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "404" in paths["/simulation-sessions/{session_id}"]["get"]["responses"]
    assert "404" in paths["/simulation-sessions/{session_id}"]["delete"]["responses"]
    assert "400" in paths["/simulation-sessions/{session_id}/changes"]["post"]["responses"]
    assert (
        "400"
        in paths["/simulation-sessions/{session_id}/changes/{change_id}"]["delete"]["responses"]
    )
    assert (
        "404" in paths["/simulation-sessions/{session_id}/projected-positions"]["get"]["responses"]
    )
    assert "404" in paths["/simulation-sessions/{session_id}/projected-summary"]["get"]["responses"]


async def test_openapi_declares_portfolio_not_found_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "404" in paths["/portfolios/{portfolio_id}"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/positions"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/transactions"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/cashflow-projection"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/position-history"]["get"]["responses"]
    assert "404" in paths["/support/portfolios/{portfolio_id}/overview"]["get"]["responses"]
    assert "404" in paths["/support/portfolios/{portfolio_id}/aggregation-jobs"]["get"]["responses"]
    assert "404" in paths["/support/portfolios/{portfolio_id}/valuation-jobs"]["get"]["responses"]
    assert "404" in paths["/lineage/portfolios/{portfolio_id}/keys"]["get"]["responses"]


async def test_openapi_hides_migrated_legacy_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/portfolios/{portfolio_id}/summary" not in paths
    assert "/portfolios/{portfolio_id}/review" not in paths
    assert "/portfolios/{portfolio_id}/risk" not in paths
    assert "/portfolios/{portfolio_id}/concentration" not in paths
    assert "/portfolios/{portfolio_id}/performance" not in paths
    assert "/portfolios/{portfolio_id}/performance/mwr" not in paths
    assert "/portfolios/{portfolio_id}/positions-analytics" not in paths


async def test_openapi_declares_core_snapshot_contract(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    endpoint = "/integration/portfolios/{portfolio_id}/core-snapshot"
    assert endpoint in paths
    responses = paths[endpoint]["post"]["responses"]
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses
    assert "409" in responses
    assert "422" in responses
