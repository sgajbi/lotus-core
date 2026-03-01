from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.analytics_inputs import (
    get_analytics_timeseries_service,
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
            },
            "page": {"next_page_token": None},
            "observations": [],
        }
    )
    mock_service.create_export_job = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "DEMO_DPM_EUR_001",
            "status": "completed",
            "request_fingerprint": "fp1",
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
            "request_fingerprint": "fp1",
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
            "generated_at": datetime(2026, 3, 1, tzinfo=UTC),
            "contract_version": "rfc_063_v1",
            "data": [],
        }
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
    mock_service.get_portfolio_timeseries.assert_awaited_once()


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
    mock_service.create_export_job.assert_awaited_once()


async def test_get_analytics_export_job_result_json_success(async_test_client):
    client, _mock_service = async_test_client
    response = await client.get(
        "/integration/exports/analytics-timeseries/jobs/aexp_1/result?result_format=json&compression=none"
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "aexp_1"
