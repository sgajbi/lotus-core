from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.source_data_products import QUERY_SERVICE, SOURCE_DATA_PRODUCT_CATALOG
from portfolio_common.source_data_security import (
    get_source_data_security_profile,
    required_source_data_capability,
)

from src.services.query_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio

SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS = {
    "tenant_id",
    "generated_at",
    "as_of_date",
    "restatement_version",
    "reconciliation_status",
    "data_quality_status",
    "latest_evidence_timestamp",
    "source_batch_fingerprint",
    "snapshot_id",
    "policy_version",
    "correlation_id",
}


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


async def test_openapi_binds_query_service_source_data_products(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.serving_plane != QUERY_SERVICE:
            continue
        for route in product.current_routes:
            operation = schema["paths"][route].get("post") or schema["paths"][route].get("get")
            assert operation is not None
            extension = operation["x-lotus-source-data-product"]
            assert extension["product_name"] == product.product_name
            assert extension["product_version"] == product.product_version
            assert extension["route_family"] == product.route_family
            assert extension["serving_plane"] == product.serving_plane
            assert extension["owner"] == product.owner
            assert extension["consumers"] == list(product.consumers)
            assert extension["current_routes"] == list(product.current_routes)
            security_extension = operation["x-lotus-source-data-security"]
            profile = get_source_data_security_profile(product.product_name)
            assert security_extension["product_name"] == product.product_name
            assert security_extension["tenant_required"] == profile.tenant_required
            assert security_extension["entitlement_required"] == profile.entitlement_required
            assert security_extension["access_classification"] == profile.access_classification
            assert security_extension["audit_requirement"] == profile.audit_requirement
            assert security_extension["required_capability"] == required_source_data_capability(
                product.product_name
            )
            assert security_extension["operator_only"] == profile.operator_only


async def test_openapi_binds_query_service_source_data_product_response_identity(
    async_test_client,
):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    components = schema["components"]["schemas"]
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.serving_plane != QUERY_SERVICE:
            continue
        for route in product.current_routes:
            operation = schema["paths"][route].get("post") or schema["paths"][route].get("get")
            response_schema_ref = operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]["$ref"]
            response_schema_name = response_schema_ref.rsplit("/", maxsplit=1)[-1]
            response_schema = components[response_schema_name]

            assert response_schema["properties"]["product_name"]["default"] == product.product_name
            assert (
                response_schema["properties"]["product_version"]["default"]
                == product.product_version
            )


async def test_openapi_exposes_holdings_as_of_runtime_supportability_metadata(
    async_test_client,
):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    components = response.json()["components"]["schemas"]

    holdings_response_schemas = [
        components["PortfolioPositionsResponse"],
        components["CashBalancesResponse"],
    ]

    for response_schema in holdings_response_schemas:
        assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(response_schema["properties"])
        assert response_schema["properties"]["product_name"]["default"] == "HoldingsAsOf"
        assert response_schema["properties"]["product_version"]["default"] == "v1"


async def test_openapi_exposes_transaction_ledger_runtime_supportability_metadata(
    async_test_client,
):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    components = response.json()["components"]["schemas"]

    ledger_response_schemas = [
        components["PaginatedTransactionResponse"],
    ]

    for response_schema in ledger_response_schemas:
        assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(response_schema["properties"])
        assert response_schema["properties"]["product_name"]["default"] == "TransactionLedgerWindow"
        assert response_schema["properties"]["product_version"]["default"] == "v1"


async def test_openapi_excludes_control_plane_analytics_input_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/integration/portfolios/{portfolio_id}/analytics/reference" not in paths
    assert "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries" not in paths
    assert "/integration/portfolios/{portfolio_id}/analytics/position-timeseries" not in paths
    assert "/integration/portfolios/{portfolio_id}/timeseries" not in paths
    assert "/integration/positions/{portfolio_id}/timeseries" not in paths


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
    assert "404" in paths["/portfolios/{portfolio_id}/cash-balances"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/positions"]["get"]["responses"]
    assert "400" in paths["/portfolios/{portfolio_id}/transactions"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/transactions"]["get"]["responses"]
    assert "400" in paths["/reporting/portfolio-summary/query"]["post"]["responses"]
    assert "404" in paths["/reporting/portfolio-summary/query"]["post"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/cash-accounts"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/cashflow-projection"]["get"]["responses"]
    assert "404" in paths["/portfolios/{portfolio_id}/position-history"]["get"]["responses"]


async def test_openapi_includes_reporting_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/reporting/assets-under-management/query" in paths
    assert "/reporting/asset-allocation/query" in paths
    assert "/portfolios/{portfolio_id}/cash-balances" in paths
    assert "/reporting/portfolio-summary/query" in paths
    assert "/portfolios/{portfolio_id}/cash-accounts" in paths


async def test_openapi_describes_reporting_and_enhanced_discovery_contracts(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    aum_query = paths["/reporting/assets-under-management/query"]["post"]
    allocation_query = paths["/reporting/asset-allocation/query"]["post"]
    portfolio_summary_query = paths["/reporting/portfolio-summary/query"]["post"]
    portfolios_query = paths["/portfolios/"]["get"]
    strategic_cash_balances_query = paths["/portfolios/{portfolio_id}/cash-balances"]["get"]
    cash_accounts_query = paths["/portfolios/{portfolio_id}/cash-accounts"]["get"]

    assert (
        "source-owned assets-under-management views for a resolved reporting scope"
        in aum_query["description"]
    )
    assert (
        "Prefer this route over reconstructing AUM from holdings rows" in aum_query["description"]
    )
    assert "strategic allocation views" in allocation_query["description"]
    assert (
        "Prefer this route over mining allocation views from `core-snapshot`"
        in allocation_query["description"]
    )
    assert (
        "strategic HoldingsAsOf cash-account balance read"
        in strategic_cash_balances_query["description"]
    )
    assert (
        "Prefer this contract for new gateway, advise, or report integrations"
        in strategic_cash_balances_query["description"]
    )
    assert "strategic historical portfolio summary" in portfolio_summary_query["description"]
    assert (
        "Prefer this route over downstream reconstruction from holdings rows or `core-snapshot`"
        in portfolio_summary_query["description"]
    )
    assert (
        "correct lotus-core summary seam for report-ready wealth totals"
        in portfolio_summary_query["description"]
    )
    assert "canonical cash-account master records" in cash_accounts_query["description"]
    assert "Do not use this route for per-account balances" in cash_accounts_query["description"]

    strategic_cash_balances_as_of_date = next(
        parameter
        for parameter in strategic_cash_balances_query["parameters"]
        if parameter["name"] == "as_of_date"
    )
    assert strategic_cash_balances_as_of_date["description"] == (
        "Optional as-of date for booked cash-account balances. "
        "When omitted, lotus-core resolves the latest booked business date."
    )

    strategic_cash_balances_reporting_currency = next(
        parameter
        for parameter in strategic_cash_balances_query["parameters"]
        if parameter["name"] == "reporting_currency"
    )
    assert strategic_cash_balances_reporting_currency["description"] == (
        "Optional reporting currency. Defaults to the portfolio currency when omitted."
    )

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
    cash_account_query_response = components["CashAccountQueryResponse"]
    transaction_record = components["TransactionRecord"]

    assert aum_request["properties"]["reporting_currency"]["description"].startswith(
        "Optional reporting currency."
    )
    assert components["AssetsUnderManagementResponse"]["properties"]["resolved_as_of_date"][
        "examples"
    ] == ["2026-03-27"]
    assert components["AssetsUnderManagementResponse"]["properties"]["reporting_currency"][
        "examples"
    ] == ["USD"]
    assert allocation_response["properties"]["look_through"]["description"].startswith(
        "Applied look-through mode"
    )
    assert allocation_response["properties"]["resolved_as_of_date"]["examples"] == ["2026-03-27"]
    assert allocation_response["properties"]["reporting_currency"]["examples"] == ["USD"]
    assert allocation_response["properties"]["total_market_value_reporting_currency"][
        "examples"
    ] == [1000000.0]
    assert cash_response["properties"]["totals"]["description"] == "Portfolio-level cash totals."
    assert cash_response["properties"]["reporting_currency"]["examples"] == ["USD"]
    assert cash_response["properties"]["resolved_as_of_date"]["examples"] == ["2026-03-27"]
    assert cash_response["properties"]["product_name"]["default"] == "HoldingsAsOf"
    assert cash_response["properties"]["product_version"]["default"] == "v1"
    assert (
        portfolio_summary_response["properties"]["snapshot_metadata"]["description"]
        == "Resolved snapshot metadata for the summary query."
    )
    assert portfolio_summary_response["properties"]["portfolio_type"]["examples"] == [
        "DISCRETIONARY"
    ]
    assert portfolio_summary_response["properties"]["risk_exposure"]["examples"] == ["BALANCED"]
    assert portfolio_summary_response["properties"]["status"]["examples"] == ["ACTIVE"]
    assert (
        portfolio_summary_query["responses"]["400"]["content"]["application/json"]["example"][
            "detail"
        ]
        == "FX rate not found for USD/SGD as of 2026-03-27."
    )
    assert (
        portfolio_summary_query["responses"]["404"]["content"]["application/json"]["example"][
            "detail"
        ]
        == "Portfolio with id PORT-001 not found"
    )
    assert cash_account_query_response["properties"]["cash_accounts"]["description"] == (
        "Canonical cash accounts linked to the portfolio."
    )
    assert cash_account_query_response["properties"]["cash_accounts"]["examples"] == [
        [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "PORT-001",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "account_role": "OPERATING_CASH",
                "lifecycle_status": "ACTIVE",
                "opened_on": "2026-01-01",
                "source_system": "lotus-manage",
            }
        ]
    ]
    portfolio_id_param = next(
        parameter
        for parameter in cash_accounts_query["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_id_param["description"] == "Portfolio identifier."
    as_of_date_param = next(
        parameter
        for parameter in cash_accounts_query["parameters"]
        if parameter["name"] == "as_of_date"
    )
    assert as_of_date_param["description"] == (
        "Optional as-of date used to filter cash-account master records by open/close window."
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
    transaction_response = schema["components"]["schemas"]["PaginatedTransactionResponse"]

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
    security_id = next(
        parameter for parameter in transactions["parameters"] if parameter["name"] == "security_id"
    )
    assert security_id["description"] == (
        "Filter by a specific security identifier for holdings drill-down and latest "
        "transaction retrieval within the portfolio."
    )
    component_type = next(
        parameter
        for parameter in transactions["parameters"]
        if parameter["name"] == "component_type"
    )
    assert component_type["description"] == "Filter by FX component type such as FX_CONTRACT_OPEN."
    reporting_currency = next(
        parameter
        for parameter in transactions["parameters"]
        if parameter["name"] == "reporting_currency"
    )
    assert reporting_currency["description"] == (
        "Optional reporting currency for restated monetary fields on each returned ledger row. "
        "Use this when a downstream needs strategic transaction rows plus reporting-currency "
        "amounts for reporting or aggregation workflows."
    )
    assert transactions["summary"] == "Get Portfolio Transactions"
    assert "strategic TransactionLedgerWindow operational read" in transactions["description"]
    assert "FX and linked-event filters" in transactions["description"]
    assert (
        "optional reporting-currency restatement for monetary fields" in transactions["description"]
    )
    assert (
        "`component_type`, `linked_transaction_group_id`, `fx_contract_id`, `swap_event_id`"
        in transactions["description"]
    )
    assert (
        "Use `reporting_currency` when a downstream reporting surface needs"
        in transactions["description"]
    )
    assert (
        "Results default to latest-first ordering by `transaction_date` descending"
        in transactions["description"]
    )
    assert (
        schema["components"]["schemas"]["TransactionRecord"]["properties"]["settlement_date"][
            "description"
        ]
        == "Canonical settlement timestamp when known. Use alongside transaction_date to "
        "differentiate trade booking from contractual or effective cash/value settlement."
    )
    assert transaction_response["properties"]["product_name"]["default"] == (
        "TransactionLedgerWindow"
    )
    assert transaction_response["properties"]["product_version"]["default"] == "v1"
    assert transaction_response["properties"]["reporting_currency"]["description"].startswith(
        "Resolved reporting currency for optional restated transaction amounts."
    )
    assert (
        schema["components"]["schemas"]["TransactionRecord"]["properties"][
            "gross_transaction_amount_reporting_currency"
        ]["description"]
        == "Gross transaction amount restated into the requested reporting currency when "
        "`reporting_currency` is supplied on the route."
    )
    assert (
        schema["components"]["schemas"]["TransactionRecord"]["properties"][
            "realized_gain_loss_reporting_currency"
        ]["description"]
        == "Transaction-level realized gain/loss restated into the requested reporting "
        "currency when `reporting_currency` is supplied on the route."
    )
    assert (
        schema["components"]["schemas"]["TransactionRecord"]["properties"][
            "realized_fx_pnl_local_reporting_currency"
        ]["description"]
        == "Transaction-level realized FX P&L local amount restated into the requested reporting "
        "currency when `reporting_currency` is supplied on the route. This is row-level "
        "source evidence, not portfolio-level FX attribution."
    )

    bad_request = transactions["responses"]["400"]["content"]["application/json"]["example"]
    assert bad_request["detail"] == "FX rate not found for USD/SGD as of 2026-03-10."
    not_found = transactions["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-TXN-001 not found"


async def test_openapi_describes_position_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    latest_positions = schema["paths"]["/portfolios/{portfolio_id}/positions"]["get"]
    position_history = schema["paths"]["/portfolios/{portfolio_id}/position-history"]["get"]
    positions_response = schema["components"]["schemas"]["PortfolioPositionsResponse"]

    positions_portfolio_id = next(
        parameter
        for parameter in latest_positions["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert positions_portfolio_id["description"] == "Portfolio identifier."
    assert "strategic HoldingsAsOf operational read" in latest_positions["description"]
    assert "gateway portfolio position books" in latest_positions["description"]
    assert "Use `as_of_date` for booked historical state" in latest_positions["description"]
    assert (
        "Do not treat this route as a substitute for performance, risk, "
        "or reporting-specific aggregation contracts" in latest_positions["description"]
    )

    include_projected = next(
        parameter
        for parameter in latest_positions["parameters"]
        if parameter["name"] == "include_projected"
    )
    assert include_projected["description"] == (
        "When true, returns the latest projected state even if future-dated transactions "
        "push holdings beyond the latest booked business_date."
    )

    as_of_date = next(
        parameter
        for parameter in latest_positions["parameters"]
        if parameter["name"] == "as_of_date"
    )
    assert as_of_date["description"] == (
        "Optional as-of date for booked position state. When omitted and "
        "`include_projected=false`, lotus-core resolves the latest booked business date."
    )

    history_security_id = next(
        parameter
        for parameter in position_history["parameters"]
        if parameter["name"] == "security_id"
    )
    assert history_security_id["description"] == (
        "Security identifier for the position-history drill-down."
    )
    assert (
        "holdings drill-down, lineage-aware troubleshooting, and historical "
        "security-level state inspection" in (position_history["description"])
    )
    assert (
        "do not use it as a substitute for the strategic latest-holdings read"
        in (position_history["description"])
    )

    positions_not_found = latest_positions["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    history_not_found = position_history["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    position_history_response = schema["components"]["schemas"]["PortfolioPositionHistoryResponse"]
    assert positions_not_found["detail"] == "Portfolio with id PORT-POS-001 not found"
    assert history_not_found["detail"] == "Portfolio with id PORT-POS-001 not found"
    assert position_history_response["properties"]["positions"]["description"] == (
        "Time-series list of position-history records for the security."
    )
    assert positions_response["properties"]["product_name"]["default"] == "HoldingsAsOf"
    assert positions_response["properties"]["product_version"]["default"] == "v1"
    assert positions_response["properties"]["positions"]["description"].startswith(
        "Governed holdings rows for the resolved HoldingsAsOf scope."
    )


async def test_openapi_describes_cashflow_projection_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    projection = schema["paths"]["/portfolios/{portfolio_id}/cashflow-projection"]["get"]
    assert "portfolio-level daily net cashflow projection" in projection["description"]
    assert (
        "forecasting, performance analytics, and advisory recommendation logic "
        "outside this contract" in projection["description"]
    )

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
        "When true, includes projected future-dated external cash movements "
        "(for example deposits and withdrawals)."
    )

    not_found = projection["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-CF-001 not found"
    projection_response = schema["components"]["schemas"]["CashflowProjectionResponse"]
    assert projection_response["properties"]["portfolio_currency"]["description"] == (
        "ISO currency code for net_cashflow, projected_cumulative_cashflow, "
        "and total_net_cashflow. Sourced from the portfolio base currency."
    )
    assert projection_response["properties"]["booked_total_net_cashflow"]["description"] == (
        "Total booked portfolio-level cashflow across returned projection points."
    )
    point_schema = schema["components"]["schemas"]["CashflowProjectionPoint"]
    assert (
        "booked_net_cashflow plus projected_settlement_cashflow"
        in (point_schema["properties"]["net_cashflow"]["description"])
    )


async def test_openapi_describes_portfolio_discovery_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    portfolio_query = schema["paths"]["/portfolios/"]["get"]
    single_portfolio = schema["paths"]["/portfolios/{portfolio_id}"]["get"]

    assert (
        "portfolio lookup, selector population, and navigation scope discovery"
        in (portfolio_query["description"])
    )
    assert (
        "do not use it as a substitute for single-portfolio detail"
        in (portfolio_query["description"])
    )
    assert "canonical portfolio identity and standing metadata" in single_portfolio["description"]
    assert (
        "do not use it as a substitute for portfolio positions" in single_portfolio["description"]
    )

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

    portfolio_query_response = components["PortfolioQueryResponse"]
    portfolio_record = components["PortfolioRecord"]
    assert portfolio_query_response["properties"]["portfolios"]["description"] == (
        "List of portfolio records matching the applied query filters."
    )
    assert portfolio_record["properties"]["objective"]["description"] == (
        "Primary client objective for this portfolio."
    )
    assert portfolio_record["properties"]["cost_basis_method"]["description"] == (
        "Portfolio-level cost-basis accounting method used by lot accounting."
    )

    not_found = single_portfolio["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Portfolio with id PORT-DISC-001 not found"


async def test_openapi_describes_reference_market_data_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    instruments = schema["paths"]["/instruments/"]["get"]
    prices = schema["paths"]["/prices/"]["get"]
    fx_rates = schema["paths"]["/fx-rates/"]["get"]

    assert "canonical security master lookup" in instruments["description"]
    assert "do not use it as a substitute for portfolio positions" in instruments["description"]
    assert "source-owned pricing history" in prices["description"]
    assert "do not use it as a substitute for performance analytics" in prices["description"]
    assert "source-owned FX conversion history" in fx_rates["description"]
    assert "do not use it as a substitute for portfolio performance" in fx_rates["description"]

    instrument_security_id = next(
        parameter for parameter in instruments["parameters"] if parameter["name"] == "security_id"
    )
    assert instrument_security_id["description"] == "Filter by a specific security identifier."

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

    instrument_response = components["PaginatedInstrumentResponse"]
    price_response = components["MarketPriceResponse"]
    fx_response = components["FxRateResponse"]
    assert instrument_response["properties"]["instruments"]["description"] == (
        "The list of instrument records for the current page."
    )
    assert price_response["properties"]["prices"]["description"] == (
        "Market price records for the requested security and date range."
    )
    assert fx_response["properties"]["rates"]["description"] == (
        "FX rate observations for the requested currency pair and date range."
    )


async def test_openapi_describes_lookup_catalog_contract_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    portfolio_lookups = schema["paths"]["/lookups/portfolios"]["get"]
    instrument_lookups = schema["paths"]["/lookups/instruments"]["get"]
    currency_lookups = schema["paths"]["/lookups/currencies"]["get"]

    assert "thin selector catalogs only" in portfolio_lookups["description"]
    assert (
        "do not use it as a substitute for canonical portfolio detail"
        in (portfolio_lookups["description"])
    )
    assert "thin selector catalogs only" in instrument_lookups["description"]
    assert (
        "do not use it as a substitute for canonical instrument reference reads"
        in (instrument_lookups["description"])
    )
    assert "selector population only" in currency_lookups["description"]
    assert "do not use it as a substitute for FX-rate history" in currency_lookups["description"]

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

    lookup_response = components["LookupResponse"]
    lookup_item = components["LookupItem"]
    assert lookup_response["properties"]["items"]["description"] == (
        "Lookup options returned for the requested catalog."
    )
    assert lookup_item["properties"]["id"]["description"] == (
        "Canonical identifier used by UI selectors."
    )
    assert lookup_item["properties"]["label"]["description"] == (
        "Display label for UI selector option."
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
    components = schema["components"]["schemas"]

    buy_lots = schema["paths"]["/portfolios/{portfolio_id}/positions/{security_id}/lots"]["get"]
    buy_offsets = schema["paths"][
        "/portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets"
    ]["get"]
    buy_cash_linkage = schema["paths"][
        "/portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage"
    ]["get"]
    sell_disposals = schema["paths"][
        "/portfolios/{portfolio_id}/positions/{security_id}/sell-disposals"
    ]["get"]
    sell_cash_linkage = schema["paths"][
        "/portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage"
    ]["get"]

    assert "do not use it as a general holdings or reporting read" in buy_lots["description"]
    assert "do not use it as a portfolio-income summary route" in buy_offsets["description"]
    assert (
        "do not use it as a general cash-balance or portfolio-cashflow read"
        in buy_cash_linkage["description"]
    )
    assert (
        "do not use it as a general performance, tax-reporting, or holdings read"
        in (sell_disposals["description"])
    )
    assert (
        "do not use it as a portfolio cashflow, liquidity, or reporting summary route"
        in (sell_cash_linkage["description"])
    )

    buy_security_id = next(
        parameter for parameter in buy_lots["parameters"] if parameter["name"] == "security_id"
    )
    assert buy_security_id["description"] == "Security identifier for the BUY-state position key."

    buy_transaction_id = next(
        parameter
        for parameter in buy_cash_linkage["parameters"]
        if parameter["name"] == "transaction_id"
    )
    assert buy_transaction_id["description"] == "Security-side BUY transaction identifier."

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
    buy_cash_not_found = buy_cash_linkage["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    sell_not_found = sell_disposals["responses"]["404"]["content"]["application/json"]["example"]
    sell_cash_not_found = sell_cash_linkage["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert buy_not_found["detail"] == (
        "BUY state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
    )
    assert buy_cash_not_found["detail"] == (
        "BUY cash linkage not found for portfolio PORT-STATE-001 and transaction TXN-BUY-2026-0001"
    )
    assert sell_not_found["detail"] == (
        "SELL state not found for portfolio PORT-STATE-001 and security SEC-US-AAPL"
    )
    assert sell_cash_not_found["detail"] == (
        "SELL cash linkage not found for portfolio PORT-STATE-001 and transaction "
        "TXN-SELL-2026-0001"
    )

    sell_disposal_record = components["SellDisposalRecord"]
    assert sell_disposal_record["properties"]["disposal_cost_basis_base"]["description"] == (
        "Disposed cost basis in portfolio base currency (absolute value)."
    )
    assert sell_disposal_record["properties"]["disposal_cost_basis_base"]["example"] == 3750.0
    assert sell_disposal_record["properties"]["net_sell_proceeds_local"]["description"] == (
        "Net SELL proceeds in trade/local currency after fees."
    )
    assert sell_disposal_record["properties"]["realized_gain_loss_local"]["example"] == 500.0
    assert sell_disposal_record["properties"]["source_system"]["description"] == (
        "Upstream source system that originated the transaction."
    )

    sell_cash_linkage_response = components["SellCashLinkageResponse"]
    assert sell_cash_linkage_response["properties"]["cashflow_amount"]["description"] == (
        "Linked settlement cashflow amount."
    )
    assert sell_cash_linkage_response["properties"]["cashflow_amount"]["example"] == 4250.0
    assert sell_cash_linkage_response["properties"]["cashflow_classification"]["description"] == (
        "Cashflow classification for the linked settlement event."
    )

    buy_cash_linkage_response = components["BuyCashLinkageResponse"]
    assert buy_cash_linkage_response["properties"]["calculation_policy_id"]["description"] == (
        "Calculation policy identifier used for BUY processing."
    )
    assert buy_cash_linkage_response["properties"]["calculation_policy_id"]["example"] == (
        "BUY_DEFAULT_POLICY"
    )
    assert buy_cash_linkage_response["properties"]["calculation_policy_version"]["example"] == (
        "1.0.0"
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
