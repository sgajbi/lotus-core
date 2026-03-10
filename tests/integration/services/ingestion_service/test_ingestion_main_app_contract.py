import httpx
import pytest
import pytest_asyncio

from src.services.ingestion_service.app import main as ingestion_main
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


async def test_openapi_describes_upload_parameters_and_shared_schemas(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    preview = schema["paths"]["/ingest/uploads/preview"]["post"]
    commit = schema["paths"]["/ingest/uploads/commit"]["post"]
    components = schema["components"]["schemas"]
    preview_body_ref = preview["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    commit_body_ref = commit["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    preview_body = components[preview_body_ref.rsplit("/", 1)[-1]]
    commit_body = components[commit_body_ref.rsplit("/", 1)[-1]]

    assert preview_body["properties"]["sample_size"]["description"] == (
        "Maximum number of valid normalized sample rows to include in the preview."
    )
    assert commit_body["properties"]["allow_partial"]["description"] == (
        "Allow valid rows to publish even when some rows fail validation."
    )

    commit_429 = commit["responses"]["429"]["content"]["application/json"]["example"]
    assert commit_429["detail"]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"

    commit_503 = commit["responses"]["503"]["content"]["application/json"]["example"]
    assert commit_503["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"

    preview_schema = components["UploadPreviewResponse"]
    commit_schema = components["UploadCommitResponse"]
    row_error_schema = components["UploadRowError"]

    assert preview_schema["properties"]["sample_rows"]["description"] == (
        "Normalized and validated sample rows for UI preview."
    )
    assert commit_schema["properties"]["published_rows"]["description"] == (
        "Count of rows published to canonical ingestion topics."
    )
    assert row_error_schema["properties"]["message"]["examples"] == ["baseCurrency is required"]


async def test_openapi_describes_portfolio_bundle_parameters_and_shared_schema(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    bundle = schema["paths"]["/ingest/portfolio-bundle"]["post"]
    components = schema["components"]["schemas"]
    bundle_schema = components["PortfolioBundleIngestionRequest"]

    adapter_disabled = bundle["responses"]["410"]["content"]["application/json"]["example"]
    assert adapter_disabled["detail"] == (
        "Portfolio bundle adapter mode is disabled in this environment."
    )

    rate_limited = bundle["responses"]["429"]["content"]["application/json"]["example"]
    assert rate_limited["detail"]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"

    mode_blocked = bundle["responses"]["503"]["content"]["application/json"]["example"]
    assert mode_blocked["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"

    assert bundle_schema["properties"]["portfolios"]["description"] == (
        "Canonical portfolio onboarding records included in the bundle."
    )
    assert bundle_schema["properties"]["transactions"]["examples"] == [
        [{"transaction_id": "TRN_001", "transaction_type": "BUY"}]
    ]


async def test_openapi_describes_reprocessing_parameters_and_shared_schema(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    reprocess = schema["paths"]["/reprocess/transactions"]["post"]
    components = schema["components"]["schemas"]

    conflict = reprocess["responses"]["409"]["content"]["application/json"]["example"]
    assert conflict["detail"]["code"] == "INGESTION_REPLAY_BLOCKED"

    rate_limited = reprocess["responses"]["429"]["content"]["application/json"]["example"]
    assert rate_limited["detail"]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"

    mode_blocked = reprocess["responses"]["503"]["content"]["application/json"]["example"]
    assert mode_blocked["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"

    reprocessing_request = components["ReprocessingRequest"]
    batch_ack = components["BatchIngestionAcceptedResponse"]

    assert reprocessing_request["properties"]["transaction_ids"]["examples"] == [
        ["TRN_001", "TRN_002"]
    ]
    assert batch_ack["properties"]["job_id"]["description"] == (
        "Asynchronous ingestion job identifier for client-side tracking."
    )


async def test_openapi_describes_remaining_ingestion_operational_responses(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]

    portfolios = paths["/ingest/portfolios"]["post"]
    single_transaction = paths["/ingest/transaction"]["post"]
    batch_transactions = paths["/ingest/transactions"]["post"]
    instruments = paths["/ingest/instruments"]["post"]
    market_prices = paths["/ingest/market-prices"]["post"]
    fx_rates = paths["/ingest/fx-rates"]["post"]
    business_dates = paths["/ingest/business-dates"]["post"]
    benchmark_assignments = paths["/ingest/benchmark-assignments"]["post"]

    assert (
        portfolios["responses"]["429"]["content"]["application/json"]["example"]["detail"]["code"]
        == "INGESTION_RATE_LIMIT_EXCEEDED"
    )
    assert (
        portfolios["responses"]["503"]["content"]["application/json"]["example"]["detail"]["code"]
        == "INGESTION_MODE_BLOCKS_WRITES"
    )

    assert (
        single_transaction["responses"]["500"]["content"]["application/json"]["example"]["detail"][
            "code"
        ]
        == "INGESTION_PUBLISH_FAILED"
    )
    assert (
        batch_transactions["responses"]["429"]["content"]["application/json"]["example"]["detail"][
            "code"
        ]
        == "INGESTION_RATE_LIMIT_EXCEEDED"
    )

    assert (
        instruments["responses"]["429"]["content"]["application/json"]["example"]["detail"]["code"]
        == "INGESTION_RATE_LIMIT_EXCEEDED"
    )
    assert (
        market_prices["responses"]["429"]["content"]["application/json"]["example"]["detail"][
            "code"
        ]
        == "INGESTION_RATE_LIMIT_EXCEEDED"
    )
    assert (
        fx_rates["responses"]["429"]["content"]["application/json"]["example"]["detail"]["code"]
        == "INGESTION_RATE_LIMIT_EXCEEDED"
    )

    business_date_422 = business_dates["responses"]["422"]["content"]["application/json"]["example"]
    assert business_date_422["detail"]["code"] == "BUSINESS_DATE_PAYLOAD_EMPTY"
    assert (
        benchmark_assignments["responses"]["503"]["content"]["application/json"]["example"][
            "detail"
        ]["code"]
        == "INGESTION_MODE_BLOCKS_WRITES"
    )


async def test_openapi_describes_business_date_shared_schema(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]
    business_date = components["BusinessDate"]
    business_date_request = components["BusinessDateIngestionRequest"]

    assert business_date["properties"]["business_date"]["description"] == (
        "Canonical business date to open for processing."
    )
    assert business_date["properties"]["calendar_code"]["examples"] == ["GLOBAL"]
    assert business_date["properties"]["source_batch_id"]["examples"] == [
        "business-dates-20260310-am"
    ]
    assert business_date_request["properties"]["business_dates"]["description"] == (
        "Business dates to register for downstream valuation and timeseries scheduling."
    )
    assert business_date_request["properties"]["business_dates"]["examples"] == [
        [
            {
                "business_date": "2026-03-10",
                "calendar_code": "GLOBAL",
                "market_code": "XSWX",
                "source_system": "lotus-manage",
                "source_batch_id": "business-dates-20260310-am",
            }
        ]
    ]


async def test_openapi_describes_portfolio_market_and_fx_shared_schemas(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    portfolio = components["Portfolio"]
    portfolio_request = components["PortfolioIngestionRequest"]
    market_price = components["MarketPrice"]
    market_price_request = components["MarketPriceIngestionRequest"]
    fx_rate = components["FxRate"]
    fx_rate_request = components["FxRateIngestionRequest"]

    assert portfolio["properties"]["portfolio_id"]["description"] == (
        "Canonical portfolio identifier used across all downstream calculators and query surfaces."
    )
    assert portfolio["properties"]["cost_basis_method"]["examples"] == ["FIFO"]
    assert portfolio_request["properties"]["portfolios"]["description"] == (
        "Canonical portfolio master records to ingest or upsert."
    )

    assert market_price["properties"]["price"]["description"] == (
        "Canonical closing or approved valuation price for the security."
    )
    assert market_price_request["properties"]["market_prices"]["examples"] == [
        [
            {
                "security_id": "SEC_AAPL",
                "price_date": "2026-03-10",
                "price": "175.5000000000",
                "currency": "USD",
            }
        ]
    ]

    assert fx_rate["properties"]["rate"]["description"] == (
        "FX conversion rate expressed as units of `to_currency` per one unit of `from_currency`."
    )
    assert fx_rate_request["properties"]["fx_rates"]["examples"] == [
        [
            {
                "from_currency": "USD",
                "to_currency": "SGD",
                "rate_date": "2026-03-10",
                "rate": "1.3500000000",
            }
        ]
    ]


async def test_openapi_describes_instrument_shared_schema(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]
    instrument = components["Instrument"]
    instrument_request = components["InstrumentIngestionRequest"]

    assert instrument["properties"]["security_id"]["description"] == (
        "Canonical security identifier used across portfolios, transactions, and valuation."
    )
    assert instrument["properties"]["contract_rate"]["examples"] == ["1.0850000000"]
    assert instrument["properties"]["ultimate_parent_issuer_name"]["examples"] == [
        "Barclays Group Holdings PLC"
    ]
    assert instrument_request["properties"]["instruments"]["description"] == (
        "Instrument master records to ingest or upsert."
    )
    assert instrument_request["properties"]["instruments"]["examples"] == [
        [
            {
                "security_id": "SEC_BARC_PERP",
                "name": "Barclays PLC 8% Perpetual",
                "isin": "US06738E2046",
                "currency": "USD",
                "product_type": "bond",
                "asset_class": "fixed_income",
                "sector": "financials",
                "country_of_risk": "GB",
                "rating": "BB+",
                "issuer_id": "ISSUER_BARC",
                "issuer_name": "Barclays PLC",
                "ultimate_parent_issuer_id": "ULTIMATE_BARC",
                "ultimate_parent_issuer_name": "Barclays Group Holdings PLC",
            }
        ]
    ]


async def test_openapi_describes_transaction_core_shared_schema(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]
    transaction = components["Transaction"]
    transaction_request = components["TransactionIngestionRequest"]

    assert transaction["properties"]["transaction_id"]["description"] == (
        "Canonical transaction identifier for ingestion, replay, and audit workflows."
    )
    assert transaction["properties"]["gross_transaction_amount"]["description"] == (
        "Gross economic amount before fees, taxes, or deductions."
    )
    assert transaction["properties"]["created_at"]["example"] == "2026-03-10T11:32:15Z"
    assert transaction_request["properties"]["transactions"]["description"] == (
        "Canonical transaction records to ingest or upsert asynchronously."
    )
    assert transaction_request["properties"]["transactions"]["examples"] == [
        [
            {
                "transaction_id": "TRN001",
                "portfolio_id": "PORT001",
                "instrument_id": "AAPL",
                "security_id": "SEC_AAPL",
                "transaction_date": "2023-01-15T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": "10.0",
                "price": "150.0",
                "gross_transaction_amount": "1500.0",
                "trade_currency": "USD",
                "currency": "USD",
                "trade_fee": "5.0",
                "settlement_date": "2023-01-17T10:00:00Z",
            }
        ]
    ]


async def test_openapi_describes_transaction_dual_leg_and_income_fields(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    transaction = response.json()["components"]["schemas"]["Transaction"]
    properties = transaction["properties"]

    assert properties["economic_event_id"]["description"] == (
        "Canonical economic event identifier that groups all legs or "
        "components of the same economic workflow."
    )
    assert properties["linked_transaction_group_id"]["description"] == (
        "Canonical linkage group identifier shared by related product and cash-leg entries."
    )
    assert properties["cash_entry_mode"]["description"] == (
        "Cash-leg handling mode. Use AUTO_GENERATE for service-generated "
        "cash legs or UPSTREAM_PROVIDED when the upstream cash entry is authoritative."
    )
    assert properties["link_type"]["description"] == (
        "Canonical relationship label between product and cash-leg entries."
    )
    assert properties["interest_direction"]["description"] == (
        "Semantic direction for INTEREST transactions. Supported values are INCOME and EXPENSE."
    )
    assert properties["net_interest_amount"]["description"] == (
        "Net interest amount supplied upstream for reconciliation against "
        "gross and deduction fields."
    )


async def test_openapi_describes_transaction_fx_fields(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    transaction = response.json()["components"]["schemas"]["Transaction"]
    properties = transaction["properties"]

    assert properties["component_type"]["description"] == (
        "Canonical FX component role within the economic event, such as "
        "cash settlement or contract open/close."
    )
    assert properties["settlement_status"]["description"] == (
        "Settlement lifecycle status for FX cash-settlement components, "
        "for example PENDING or SETTLED."
    )
    assert properties["fx_contract_id"]["description"] == (
        "Stable FX contract identifier used to group open, close, and "
        "settlement components for the same forward or swap contract."
    )
    assert properties["swap_event_id"]["description"] == (
        "Stable economic event identifier shared by all legs and "
        "settlement components of the same FX swap."
    )
    assert properties["fx_realized_pnl_mode"]["description"] == (
        "Policy-driven mode for realized FX P&L population, for example "
        "NONE or UPSTREAM_PROVIDED."
    )
    assert properties["realized_total_pnl_base"]["description"] == (
        "Total realized P&L translated into portfolio base currency."
    )


async def test_openapi_excludes_event_replay_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/ingestion/jobs" not in paths
    assert "/ingestion/dlq/consumer-events" not in paths
    assert "/ingestion/health/policy" not in paths


async def test_ingestion_service_fails_startup_when_kafka_init_fails(monkeypatch):
    def raise_kafka_init_error():
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(ingestion_main, "get_kafka_producer", raise_kafka_init_error)
    ingestion_main.app_state.clear()

    with pytest.raises(RuntimeError, match="Kafka producer initialization failed"):
        async with app.router.lifespan_context(app):
            pass
