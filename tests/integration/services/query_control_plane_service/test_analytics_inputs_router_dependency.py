import gzip
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_control_plane_service.app.main import app
from src.services.query_control_plane_service.app.routers.analytics_inputs import (
    get_analytics_timeseries_service,
)
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsInputError,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = MagicMock()
    mock_service.get_portfolio_timeseries = AsyncMock(
        return_value={
            "portfolio_id": "DEMO_DPM_EUR_001",
            "portfolio_currency": "EUR",
            "reporting_currency": "EUR",
            "portfolio_open_date": "2020-01-01",
            "portfolio_close_date": None,
            "performance_end_date": "2025-12-31",
            "resolved_window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "frequency": "daily",
            "contract_version": "rfc_063_v1",
            "calendar_id": "business_date_calendar",
            "missing_observation_policy": "strict",
            "lineage": {
                "generated_by": "integration.analytics_inputs",
                "generated_at": datetime(2026, 3, 1, tzinfo=UTC),
                "request_fingerprint": "abc",
                "data_version": "state_inputs_v1",
            },
            "diagnostics": {
                "quality_status_distribution": {"final": 1},
                "missing_dates_count": 0,
                "stale_points_count": 0,
                "expected_business_dates_count": 1,
                "returned_observation_dates_count": 1,
                "cash_flows_included": True,
            },
            "page": {
                "page_size": 100,
                "returned_row_count": 0,
                "sort_key": "valuation_date:asc",
                "request_scope_fingerprint": "scope-abc",
                "snapshot_epoch": 0,
                "next_page_token": None,
            },
            "observations": [],
            **source_data_product_runtime_metadata(as_of_date=date(2025, 12, 31)),
        }
    )
    mock_service.get_position_timeseries = AsyncMock(
        return_value={
            "portfolio_id": "DEMO_DPM_EUR_001",
            "portfolio_currency": "EUR",
            "reporting_currency": "EUR",
            "resolved_window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "frequency": "daily",
            "contract_version": "rfc_063_v1",
            "calendar_id": "business_date_calendar",
            "missing_observation_policy": "strict",
            "lineage": {
                "generated_by": "integration.analytics_inputs",
                "generated_at": datetime(2026, 3, 1, tzinfo=UTC),
                "request_fingerprint": "def",
                "data_version": "state_inputs_v1",
            },
            "diagnostics": {
                "quality_status_distribution": {"final": 1},
                "missing_dates_count": 0,
                "stale_points_count": 0,
                "requested_dimensions": ["asset_class"],
                "cash_flows_included": True,
            },
            "page": {
                "page_size": 100,
                "returned_row_count": 0,
                "sort_key": "valuation_date:asc,security_id:asc",
                "request_scope_fingerprint": "scope-def",
                "snapshot_epoch": 0,
                "next_page_token": None,
            },
            "rows": [],
            **source_data_product_runtime_metadata(as_of_date=date(2025, 12, 31)),
        }
    )
    mock_service.get_portfolio_reference = AsyncMock(
        return_value={
            "portfolio_id": "DEMO_DPM_EUR_001",
            "resolved_as_of_date": "2025-12-31",
            "portfolio_currency": "EUR",
            "portfolio_open_date": "2020-01-01",
            "portfolio_close_date": None,
            "performance_end_date": "2025-12-31",
            "client_id": "CIF_100234",
            "booking_center_code": "SGPB",
            "portfolio_type": "discretionary",
            "objective": "Balanced growth",
            "reference_state_policy": "current_portfolio_reference_state",
            "lineage": {
                "generated_by": "integration.analytics_inputs",
                "generated_at": datetime(2026, 3, 1, tzinfo=UTC),
                "request_fingerprint": "abc",
                "data_version": "state_inputs_v1",
            },
            "contract_version": "rfc_063_v1",
            "supported_grouping_dimensions": ["asset_class", "sector", "country"],
            **source_data_product_runtime_metadata(as_of_date=date(2025, 12, 31)),
        }
    )
    mock_service.create_export_job = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "DEMO_DPM_EUR_001",
            "status": "completed",
            "disposition": "created",
            "lifecycle_mode": "inline_job_execution",
            "request_fingerprint": "fp1",
            "result_available": True,
            "result_endpoint": "/integration/exports/analytics-timeseries/jobs/aexp_1/result",
            "result_format": "json",
            "compression": "none",
            "result_row_count": 1,
            "error_message": None,
            "created_at": datetime(2026, 3, 1, tzinfo=UTC),
            "started_at": datetime(2026, 3, 1, tzinfo=UTC),
            "completed_at": datetime(2026, 3, 1, tzinfo=UTC),
        }
    )
    mock_service.get_export_job = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "DEMO_DPM_EUR_001",
            "status": "completed",
            "disposition": "status_lookup",
            "lifecycle_mode": "inline_job_execution",
            "request_fingerprint": "fp1",
            "result_available": True,
            "result_endpoint": "/integration/exports/analytics-timeseries/jobs/aexp_1/result",
            "result_format": "json",
            "compression": "none",
            "result_row_count": 1,
            "error_message": None,
            "created_at": datetime(2026, 3, 1, tzinfo=UTC),
            "started_at": datetime(2026, 3, 1, tzinfo=UTC),
            "completed_at": datetime(2026, 3, 1, tzinfo=UTC),
        }
    )
    mock_service.get_export_result_json = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "request_fingerprint": "fp1",
            "lifecycle_mode": "inline_job_execution",
            "generated_at": datetime(2026, 3, 1, tzinfo=UTC),
            "contract_version": "rfc_063_v1",
            "result_row_count": 1,
            "data": [],
        }
    )
    mock_service.get_export_result_ndjson = AsyncMock(
        return_value=(gzip.compress(b'{"row":1}\n'), "application/x-ndjson", "gzip")
    )

    app.dependency_overrides[get_analytics_timeseries_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_analytics_timeseries_service, None)


async def test_portfolio_analytics_timeseries_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/portfolio-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
            "page": {"page_size": 100, "page_token": None},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert body["product_name"] == "PortfolioTimeseriesInput"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2025-12-31"
    assert body["portfolio_currency"] == "EUR"
    assert body["reporting_currency"] == "EUR"
    assert body["calendar_id"] == "business_date_calendar"
    assert body["missing_observation_policy"] == "strict"
    assert body["diagnostics"]["cash_flows_included"] is True
    assert body["page"]["page_size"] == 100
    assert body["page"]["request_scope_fingerprint"] == "scope-abc"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_service.get_portfolio_timeseries.assert_awaited_once()
    portfolio_call = mock_service.get_portfolio_timeseries.await_args.kwargs
    assert portfolio_call["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert portfolio_call["request"].as_of_date == date(2025, 12, 31)
    assert portfolio_call["request"].window.start_date == date(2025, 1, 1)
    assert portfolio_call["request"].window.end_date == date(2025, 1, 31)
    assert portfolio_call["request"].reporting_currency == "EUR"
    assert portfolio_call["request"].frequency == "daily"
    assert portfolio_call["request"].consumer_system == "lotus-performance"
    assert portfolio_call["request"].page.page_size == 100


async def test_portfolio_analytics_timeseries_invalid_request_maps_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_timeseries = AsyncMock(
        side_effect=AnalyticsInputError(
            "INVALID_REQUEST", "Page token does not match request scope."
        )
    )

    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/portfolio-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
            "page": {"page_size": 100, "page_token": "invalid-token"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Page token does not match request scope."


async def test_portfolio_analytics_timeseries_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_timeseries = AsyncMock(
        side_effect=AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
    )

    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/portfolio-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found."


async def test_portfolio_analytics_timeseries_insufficient_data_maps_to_422(
    async_test_client,
):
    client, mock_service = async_test_client
    mock_service.get_portfolio_timeseries = AsyncMock(
        side_effect=AnalyticsInputError(
            "INSUFFICIENT_DATA", "Missing FX rate for EUR/USD on 2025-01-31."
        )
    )

    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/portfolio-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Missing FX rate for EUR/USD on 2025-01-31."


async def test_position_analytics_timeseries_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/position-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
            "dimensions": ["asset_class"],
            "page": {"page_size": 100, "page_token": None},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert body["product_name"] == "PositionTimeseriesInput"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2025-12-31"
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    mock_service.get_position_timeseries.assert_awaited_once()
    position_call = mock_service.get_position_timeseries.await_args.kwargs
    assert position_call["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert position_call["request"].as_of_date == date(2025, 12, 31)
    assert position_call["request"].window.start_date == date(2025, 1, 1)
    assert position_call["request"].window.end_date == date(2025, 1, 31)
    assert position_call["request"].reporting_currency == "EUR"
    assert position_call["request"].frequency == "daily"
    assert position_call["request"].consumer_system == "lotus-performance"
    assert position_call["request"].dimensions == ["asset_class"]
    assert position_call["request"].page.page_size == 100


async def test_position_analytics_timeseries_insufficient_data_maps_to_422(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_timeseries = AsyncMock(
        side_effect=AnalyticsInputError(
            "INSUFFICIENT_DATA", "Missing FX rate for EUR/USD on 2025-01-31."
        )
    )

    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/position-timeseries",
        json={
            "as_of_date": "2025-12-31",
            "window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "reporting_currency": "EUR",
            "frequency": "daily",
            "consumer_system": "lotus-performance",
            "dimensions": ["asset_class"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Missing FX rate for EUR/USD on 2025-01-31."


async def test_portfolio_analytics_reference_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/reference",
        json={
            "as_of_date": "2025-12-31",
            "consumer_system": "lotus-performance",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "PortfolioAnalyticsReference"
    assert body["product_version"] == "v1"
    assert body["as_of_date"] == "2025-12-31"
    assert body["generated_at"].endswith("Z")
    assert body["reconciliation_status"] == "UNKNOWN"
    assert body["data_quality_status"] == "UNKNOWN"
    assert body["resolved_as_of_date"] == "2025-12-31"
    assert body["reference_state_policy"] == "current_portfolio_reference_state"
    mock_service.get_portfolio_reference.assert_awaited_once()
    reference_call = mock_service.get_portfolio_reference.await_args.kwargs
    assert reference_call["portfolio_id"] == "DEMO_DPM_EUR_001"
    assert reference_call["request"].as_of_date == date(2025, 12, 31)
    assert reference_call["request"].consumer_system == "lotus-performance"


async def test_portfolio_analytics_reference_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_reference = AsyncMock(
        side_effect=AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
    )

    response = await client.post(
        "/integration/portfolios/DEMO_DPM_EUR_001/analytics/reference",
        json={
            "as_of_date": "2025-12-31",
            "consumer_system": "lotus-performance",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found."


async def test_create_analytics_export_job_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.post(
        "/integration/exports/analytics-timeseries/jobs",
        json={
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "DEMO_DPM_EUR_001",
            "portfolio_timeseries_request": {
                "as_of_date": "2025-12-31",
                "period": "one_month",
            },
            "result_format": "json",
            "compression": "none",
            "consumer_system": "lotus-performance",
        },
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "aexp_1"
    assert response.json()["lifecycle_mode"] == "inline_job_execution"
    assert response.json()["result_available"] is True
    mock_service.create_export_job.assert_awaited_once()
    export_request = mock_service.create_export_job.await_args.args[0]
    assert export_request.dataset_type == "portfolio_timeseries"
    assert export_request.portfolio_id == "DEMO_DPM_EUR_001"
    assert export_request.portfolio_timeseries_request.as_of_date == date(2025, 12, 31)
    assert export_request.portfolio_timeseries_request.period == "one_month"
    assert export_request.result_format == "json"
    assert export_request.compression == "none"
    assert export_request.consumer_system == "lotus-performance"


async def test_create_analytics_export_job_invalid_request_maps_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.create_export_job = AsyncMock(
        side_effect=AnalyticsInputError(
            "INVALID_REQUEST", "Exactly one of window or period must be provided."
        )
    )

    response = await client.post(
        "/integration/exports/analytics-timeseries/jobs",
        json={
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "DEMO_DPM_EUR_001",
            "portfolio_timeseries_request": {
                "as_of_date": "2025-12-31",
                "period": "one_month",
            },
            "result_format": "json",
            "compression": "none",
            "consumer_system": "lotus-performance",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Exactly one of window or period must be provided."


async def test_get_analytics_export_job_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/integration/exports/analytics-timeseries/jobs/aexp_1")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "aexp_1"
    assert body["disposition"] == "status_lookup"
    assert body["result_available"] is True
    mock_service.get_export_job.assert_awaited_once_with("aexp_1")


async def test_get_analytics_export_job_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_export_job = AsyncMock(
        side_effect=AnalyticsInputError("RESOURCE_NOT_FOUND", "Export job not found.")
    )

    response = await client.get("/integration/exports/analytics-timeseries/jobs/aexp_404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Export job not found."


async def test_get_analytics_export_job_result_json_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get(
        "/integration/exports/analytics-timeseries/jobs/aexp_1/result?result_format=json&compression=none"
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "aexp_1"
    assert response.json()["result_row_count"] == 1
    mock_service.get_export_result_json.assert_awaited_once_with("aexp_1")


async def test_get_analytics_export_job_result_ndjson_gzip_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get(
        "/integration/exports/analytics-timeseries/jobs/aexp_1/result?result_format=ndjson&compression=gzip"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["content-encoding"] == "gzip"
    assert response.content == b'{"row":1}\n'
    mock_service.get_export_result_ndjson.assert_awaited_once_with(
        "aexp_1",
        compression="gzip",
    )


async def test_get_analytics_export_job_result_incomplete_maps_to_422(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_export_result_json = AsyncMock(
        side_effect=AnalyticsInputError(
            "INSUFFICIENT_DATA", "Export job JOB-AN-0001 is not complete."
        )
    )

    response = await client.get(
        "/integration/exports/analytics-timeseries/jobs/aexp_1/result?result_format=json&compression=none"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Export job JOB-AN-0001 is not complete."
