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


async def test_openapi_excludes_control_plane_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/simulation-sessions/{session_id}" not in paths
    assert "/integration/capabilities" not in paths
    assert "/integration/portfolios/{portfolio_id}/core-snapshot" not in paths
    assert "/support/portfolios/{portfolio_id}/overview" not in paths
    assert "/lineage/portfolios/{portfolio_id}/keys" not in paths


async def test_openapi_declares_portfolio_not_found_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "404" in paths["/portfolios/{portfolio_id}"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/positions"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/transactions"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/cashflow-projection"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/position-history"]["get"]["responses"]


async def test_openapi_describes_transaction_filters_and_not_found_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    transactions = schema["paths"]["/portfolios/{portfolio_id}/transactions"]["get"]

    portfolio_param = next(
        parameter for parameter in transactions["parameters"] if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == "Portfolio identifier."

    transaction_type = next(
        parameter
        for parameter in transactions["parameters"]
        if parameter["name"] == "transaction_type"
    )
    assert transaction_type["description"] == (
        "Filter by canonical transaction type, including FX business types."
    )

    fx_contract_id = next(
        parameter
        for parameter in transactions["parameters"]
        if parameter["name"] == "fx_contract_id"
    )
    assert fx_contract_id["description"] == "Filter by FX contract identifier."

    not_found = transactions["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-TXN-001 not found"


async def test_openapi_describes_position_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    latest_positions = schema["paths"]["/portfolios/{portfolio_id}/positions"]["get"]
    position_history = schema["paths"]["/portfolios/{portfolio_id}/position-history"]["get"]

    positions_portfolio_id = next(
        parameter
        for parameter in latest_positions["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert positions_portfolio_id["description"] == "Portfolio identifier."

    include_projected = next(
        parameter
        for parameter in latest_positions["parameters"]
        if parameter["name"] == "include_projected"
    )
    assert include_projected["description"] == (
        "When true, includes future-dated projected position state "
        "beyond current business_date."
    )

    history_security_id = next(
        parameter
        for parameter in position_history["parameters"]
        if parameter["name"] == "security_id"
    )
    assert history_security_id["description"] == (
        "Security identifier for the position-history drill-down."
    )

    positions_not_found = latest_positions["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    history_not_found = position_history["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert positions_not_found["detail"] == "Portfolio with id PORT-POS-001 not found"
    assert history_not_found["detail"] == "Portfolio with id PORT-POS-001 not found"


async def test_openapi_describes_cashflow_projection_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    projection = schema["paths"]["/portfolios/{portfolio_id}/cashflow-projection"]["get"]

    portfolio_id = next(
        parameter for parameter in projection["parameters"] if parameter["name"] == "portfolio_id"
    )
    assert portfolio_id["description"] == "Portfolio identifier."

    horizon_days = next(
        parameter for parameter in projection["parameters"] if parameter["name"] == "horizon_days"
    )
    assert horizon_days["description"] == "Projection window in days from as_of_date."

    include_projected = next(
        parameter
        for parameter in projection["parameters"]
        if parameter["name"] == "include_projected"
    )
    assert include_projected["description"] == (
        "When true, includes projected future-dated cashflows."
    )

    not_found = projection["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-CF-001 not found"


async def test_openapi_describes_portfolio_discovery_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    portfolio_query = schema["paths"]["/portfolios/"]["get"]
    single_portfolio = schema["paths"]["/portfolios/{portfolio_id}"]["get"]

    client_id = next(
        parameter for parameter in portfolio_query["parameters"] if parameter["name"] == "client_id"
    )
    assert client_id["description"] == (
        "Filter by the client grouping ID (CIF) to get all portfolios for a client."
    )

    booking_center_code = next(
        parameter
        for parameter in portfolio_query["parameters"]
        if parameter["name"] == "booking_center_code"
    )
    assert booking_center_code["description"] == (
        "Filter by booking center to get all portfolios for a business unit."
    )

    portfolio_id = next(
        parameter
        for parameter in single_portfolio["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_id["description"] == "Portfolio identifier."

    not_found = single_portfolio["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-DISC-001 not found"


async def test_openapi_describes_reference_market_data_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    prices = schema["paths"]["/prices/"]["get"]
    fx_rates = schema["paths"]["/fx-rates/"]["get"]

    security_id = next(
        parameter for parameter in prices["parameters"] if parameter["name"] == "security_id"
    )
    assert security_id["description"] == "Security identifier for the market-price series request."

    from_currency = next(
        parameter for parameter in fx_rates["parameters"] if parameter["name"] == "from_currency"
    )
    assert from_currency["description"] == "Base currency code for the requested FX series."

    to_currency = next(
        parameter for parameter in fx_rates["parameters"] if parameter["name"] == "to_currency"
    )
    assert to_currency["description"] == "Quote currency code for the requested FX series."


async def test_openapi_describes_lookup_catalog_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    portfolio_lookups = schema["paths"]["/lookups/portfolios"]["get"]
    instrument_lookups = schema["paths"]["/lookups/instruments"]["get"]
    currency_lookups = schema["paths"]["/lookups/currencies"]["get"]

    portfolio_client_id = next(
        parameter
        for parameter in portfolio_lookups["parameters"]
        if parameter["name"] == "client_id"
    )
    assert portfolio_client_id["description"] == "Optional CIF filter for tenant/client scoping."

    instrument_product_type = next(
        parameter
        for parameter in instrument_lookups["parameters"]
        if parameter["name"] == "product_type"
    )
    assert instrument_product_type["description"] == (
        "Optional product type filter (for example: Equity, Bond)."
    )

    currency_source = next(
        parameter for parameter in currency_lookups["parameters"] if parameter["name"] == "source"
    )
    assert currency_source["description"] == (
        "Currency source scope. Use ALL, PORTFOLIOS, or INSTRUMENTS."
    )


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
