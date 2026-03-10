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
    assert row_error_schema["properties"]["message"]["examples"] == [
        "baseCurrency is required"
    ]


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

    assert portfolios["responses"]["429"]["content"]["application/json"]["example"]["detail"][
        "code"
    ] == "INGESTION_RATE_LIMIT_EXCEEDED"
    assert portfolios["responses"]["503"]["content"]["application/json"]["example"]["detail"][
        "code"
    ] == "INGESTION_MODE_BLOCKS_WRITES"

    assert single_transaction["responses"]["500"]["content"]["application/json"]["example"][
        "detail"
    ]["code"] == "INGESTION_PUBLISH_FAILED"
    assert batch_transactions["responses"]["429"]["content"]["application/json"]["example"][
        "detail"
    ]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"

    assert instruments["responses"]["429"]["content"]["application/json"]["example"]["detail"][
        "code"
    ] == "INGESTION_RATE_LIMIT_EXCEEDED"
    assert market_prices["responses"]["429"]["content"]["application/json"]["example"][
        "detail"
    ]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"
    assert fx_rates["responses"]["429"]["content"]["application/json"]["example"]["detail"][
        "code"
    ] == "INGESTION_RATE_LIMIT_EXCEEDED"

    business_date_422 = business_dates["responses"]["422"]["content"]["application/json"]["example"]
    assert business_date_422["detail"]["code"] == "BUSINESS_DATE_PAYLOAD_EMPTY"
    assert benchmark_assignments["responses"]["503"]["content"]["application/json"]["example"][
        "detail"
    ]["code"] == "INGESTION_MODE_BLOCKS_WRITES"


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
