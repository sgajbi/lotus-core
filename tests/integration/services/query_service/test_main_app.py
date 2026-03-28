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


async def test_middleware_replaces_unset_lineage_headers(async_test_client):
    with patch(
        "src.services.query_service.app.main.generate_correlation_id",
        side_effect=["QRY-abc", "REQ-abc"],
    ):
        response = await async_test_client.get(
            "/openapi.json",
            headers={
                "X-Correlation-ID": "<not-set>",
                "X-Request-Id": "",
                "X-Trace-Id": "<not-set>",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QRY-abc"
    assert response.headers["X-Request-Id"] == "REQ-abc"
    assert response.headers["X-Trace-Id"] not in ("", "<not-set>")


async def test_middleware_replaces_invalid_trace_id(async_test_client):
    with patch(
        "src.services.query_service.app.main.generate_correlation_id",
        return_value="QRY-abc",
    ):
        response = await async_test_client.get(
            "/openapi.json",
            headers={
                "X-Correlation-ID": "corr-123",
                "X-Request-Id": "req-123",
                "X-Trace-Id": "trace-123",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"
    assert response.headers["X-Request-Id"] == "req-123"
    assert response.headers["X-Trace-Id"] != "trace-123"
    assert len(response.headers["X-Trace-Id"]) == 32
    assert response.headers["traceparent"].startswith(
        f"00-{response.headers['X-Trace-Id']}-0000000000000001-01"
    )


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
    assert "404" in paths["/portfolios/{portfolio_id}/cash-accounts"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/cashflow-projection"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/position-history"]["get"]["responses"]


async def test_openapi_includes_reporting_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/reporting/assets-under-management/query" in paths
    assert "/reporting/asset-allocation/query" in paths
    assert "/reporting/cash-balances/query" in paths
    assert "/reporting/portfolio-summary/query" in paths
    assert "/reporting/holdings-snapshot/query" in paths
    assert "/reporting/income-summary/query" in paths
    assert "/reporting/activity-summary/query" in paths
    assert "/portfolios/{portfolio_id}/cash-accounts" in paths


async def test_openapi_describes_reporting_and_enhanced_discovery_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    aum_query = paths["/reporting/assets-under-management/query"]["post"]
    allocation_query = paths["/reporting/asset-allocation/query"]["post"]
    cash_query = paths["/reporting/cash-balances/query"]["post"]
    portfolio_summary_query = paths["/reporting/portfolio-summary/query"]["post"]
    holdings_snapshot_query = paths["/reporting/holdings-snapshot/query"]["post"]
    income_query = paths["/reporting/income-summary/query"]["post"]
    activity_query = paths["/reporting/activity-summary/query"]["post"]
    portfolios_query = paths["/portfolios/"]["get"]
    cash_accounts_query = paths["/portfolios/{portfolio_id}/cash-accounts"]["get"]

    assert (
        "single portfolio, an explicit portfolio list, or a business unit"
        in aum_query["description"]
    )
    assert "classification dimensions" in allocation_query["description"]
    assert "portfolio currency and reporting currency" in cash_query["description"]
    assert "true historical as-of portfolio summary" in portfolio_summary_query["description"]
    assert "true historical as-of holdings snapshot" in holdings_snapshot_query["description"]
    assert "requested reporting window and year-to-date" in income_query["description"]
    assert "portfolio-level flow buckets" in activity_query["description"]
    assert "canonical cash-account master records" in cash_accounts_query["description"]

    portfolio_ids = next(
        parameter
        for parameter in portfolios_query["parameters"]
        if parameter["name"] == "portfolio_ids"
    )
    assert portfolio_ids["description"] == "Filter by an explicit portfolio identifier list."

    aum_request = components["AssetsUnderManagementQueryRequest"]
    allocation_response = components["AssetAllocationResponse"]
    cash_response = components["CashBalancesResponse"]
    portfolio_summary_response = components["PortfolioSummaryResponse"]
    holdings_snapshot_response = components["HoldingsSnapshotResponse"]
    income_response = components["IncomeSummaryResponse"]
    activity_response = components["ActivitySummaryResponse"]
    cash_account_query_response = components["CashAccountQueryResponse"]
    transaction_record = components["TransactionRecord"]

    assert aum_request["properties"]["reporting_currency"]["description"].startswith(
        "Optional reporting currency."
    )
    assert allocation_response["properties"]["look_through"]["description"].startswith(
        "Applied look-through mode"
    )
    assert cash_response["properties"]["totals"]["description"] == "Portfolio-level cash totals."
    assert (
        portfolio_summary_response["properties"]["snapshot_metadata"]["description"]
        == "Resolved snapshot metadata for the summary query."
    )
    assert holdings_snapshot_response["properties"]["positions"]["description"].startswith(
        "Holdings snapshot rows"
    )
    assert income_response["properties"]["totals"]["description"] == "Scope-level income totals."
    assert (
        activity_response["properties"]["totals"]["description"] == "Scope-level activity totals."
    )
    assert cash_account_query_response["properties"]["cash_accounts"]["description"] == (
        "Canonical cash accounts linked to the portfolio."
    )
    assert transaction_record["properties"]["trade_fee"]["description"] == (
        "Primary trade fee recorded directly on the transaction."
    )
    assert transaction_record["properties"]["costs"]["description"] == (
        "Detailed transaction costs associated with the transaction."
    )


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

    instrument_id = next(
        parameter
        for parameter in transactions["parameters"]
        if parameter["name"] == "instrument_id"
    )
    assert instrument_id["description"] == "Filter by a specific instrument identifier."
    assert transactions["summary"] == "Get Transactions for a Portfolio"
    assert (
        schema["components"]["schemas"]["TransactionRecord"]["properties"]["settlement_date"][
            "description"
        ]
        == "Canonical settlement timestamp when known. Use alongside transaction_date to "
        "differentiate trade booking from contractual or effective cash/value settlement."
    )

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
        "When true, includes future-dated projected position state beyond current business_date."
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


async def test_openapi_describes_instrument_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    instruments = schema["paths"]["/instruments/"]["get"]
    record = schema["components"]["schemas"]["InstrumentRecord"]

    security_id = next(
        parameter for parameter in instruments["parameters"] if parameter["name"] == "security_id"
    )
    assert security_id["description"] == "Filter by a specific security identifier."

    product_type = next(
        parameter for parameter in instruments["parameters"] if parameter["name"] == "product_type"
    )
    assert product_type["description"] == (
        "Filter by a specific product type such as Equity or Bond."
    )

    assert record["properties"]["security_id"]["description"] == "Canonical security identifier."
    assert record["properties"]["pair_base_currency"]["description"] == (
        "FX pair base currency when the record represents an FX contract instrument."
    )


async def test_openapi_describes_buy_sell_state_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    buy_lots = schema["paths"]["/portfolios/{portfolio_id}/positions/{security_id}/lots"]["get"]
    sell_disposals = schema["paths"][
        "/portfolios/{portfolio_id}/positions/{security_id}/sell-disposals"
    ]["get"]
    sell_cash_linkage = schema["paths"][
        "/portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage"
    ]["get"]

    buy_security_id = next(
        parameter for parameter in buy_lots["parameters"] if parameter["name"] == "security_id"
    )
    assert buy_security_id["description"] == "Security identifier for the BUY-state position key."

    sell_security_id = next(
        parameter
        for parameter in sell_disposals["parameters"]
        if parameter["name"] == "security_id"
    )
    assert sell_security_id["description"] == "Security identifier for the SELL-state position key."

    sell_transaction_id = next(
        parameter
        for parameter in sell_cash_linkage["parameters"]
        if parameter["name"] == "transaction_id"
    )
    assert sell_transaction_id["description"] == "Security-side SELL transaction identifier."

    buy_not_found = buy_lots["responses"]["404"]["content"]["application/json"]["example"]
    sell_not_found = sell_disposals["responses"]["404"]["content"]["application/json"]["example"]
    assert buy_not_found["detail"] == (
        "BUY state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
    )
    assert sell_not_found["detail"] == (
        "SELL state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
    )


async def test_openapi_describes_shared_read_model_field_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    portfolio_record = components["PortfolioRecord"]
    market_price_record = components["MarketPriceRecord"]
    fx_rate_record = components["FxRateRecord"]
    lookup_item = components["LookupItem"]

    assert portfolio_record["properties"]["base_currency"]["description"] == (
        "ISO base currency code."
    )
    assert portfolio_record["properties"]["status"]["description"] == (
        "Portfolio lifecycle status."
    )

    assert market_price_record["properties"]["price_date"]["description"] == (
        "Business date of the market price observation."
    )
    assert market_price_record["properties"]["price"]["description"] == (
        "Observed market price for the security on the given date."
    )

    assert fx_rate_record["properties"]["rate_date"]["description"] == (
        "Business date of the FX rate observation."
    )
    assert fx_rate_record["properties"]["rate"]["description"] == (
        "Observed FX rate for the requested currency pair on the given date."
    )

    assert lookup_item["properties"]["id"]["description"] == (
        "Canonical identifier used by UI selectors."
    )
    assert lookup_item["properties"]["label"]["description"] == (
        "Display label for UI selector option."
    )


async def test_openapi_describes_position_cashflow_and_valuation_schema_depth(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    components = response.json()["components"]["schemas"]

    cashflow = components["CashflowRecord"]
    valuation = components["ValuationData"]
    position_history = components["PositionHistoryRecord"]

    assert cashflow["properties"]["amount"]["description"] == (
        "Signed cashflow amount expressed in the reported cashflow currency."
    )
    assert cashflow["properties"]["classification"]["description"] == (
        "Canonical cashflow classification used by analytics and reporting."
    )

    assert valuation["properties"]["market_price"]["description"] == (
        "Market price used for the position valuation snapshot."
    )
    assert valuation["properties"]["unrealized_gain_loss"]["description"] == (
        "Unrealized gain or loss in portfolio base currency."
    )

    assert position_history["properties"]["transaction_id"]["description"] == (
        "Transaction identifier that produced this position-history state."
    )
    assert position_history["properties"]["cost_basis_local"]["description"] == (
        "Total cost basis in the instrument's local currency."
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
