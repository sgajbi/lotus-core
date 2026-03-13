from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.main import app
from src.services.query_control_plane_service.app.routers.operations import (
    OperationsService,
    get_operations_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_operations_service = AsyncMock()
    app.dependency_overrides[get_operations_service] = lambda: mock_operations_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_operations_service
    app.dependency_overrides.pop(get_operations_service, None)


async def test_support_overview_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_support_overview.return_value = {
        "portfolio_id": "P1",
        "business_date": date(2025, 8, 31),
        "current_epoch": 3,
        "active_reprocessing_keys": 1,
        "pending_valuation_jobs": 2,
        "processing_valuation_jobs": 1,
        "stale_processing_valuation_jobs": 0,
        "failed_valuation_jobs": 0,
        "oldest_pending_valuation_date": date(2025, 8, 30),
        "valuation_backlog_age_days": 1,
        "pending_aggregation_jobs": 0,
        "processing_aggregation_jobs": 0,
        "stale_processing_aggregation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "oldest_pending_aggregation_date": None,
        "aggregation_backlog_age_days": None,
        "pending_analytics_export_jobs": 2,
        "processing_analytics_export_jobs": 1,
        "stale_processing_analytics_export_jobs": 0,
        "failed_analytics_export_jobs": 1,
        "oldest_pending_analytics_export_created_at": "2025-08-31T10:00:00Z",
        "analytics_export_backlog_age_minutes": 15,
        "latest_transaction_date": date(2025, 8, 31),
        "latest_booked_transaction_date": date(2025, 8, 31),
        "latest_position_snapshot_date": date(2025, 8, 31),
        "latest_booked_position_snapshot_date": date(2025, 8, 31),
        "position_snapshot_history_mismatch_count": 0,
        "controls_business_date": date(2025, 8, 31),
        "controls_epoch": 3,
        "controls_status": "COMPLETED",
        "controls_blocking": False,
        "publish_allowed": True,
    }

    response = await client.get("/support/portfolios/P1/overview")

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["publish_allowed"] is True
    assert "X-Correlation-ID" in response.headers


async def test_support_overview_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_support_overview.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/overview")

    assert response.status_code == 500
    assert "support overview" in response.json()["detail"].lower()


async def test_calculator_slos_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_calculator_slos.return_value = {
        "portfolio_id": "P1",
        "business_date": date(2025, 8, 31),
        "stale_threshold_minutes": 15,
        "generated_at_utc": "2026-03-03T10:05:11Z",
        "valuation": {
            "pending_jobs": 2,
            "processing_jobs": 1,
            "stale_processing_jobs": 0,
            "failed_jobs": 0,
            "failed_jobs_last_24h": 0,
            "oldest_open_job_date": date(2025, 8, 31),
            "backlog_age_days": 0,
        },
        "aggregation": {
            "pending_jobs": 1,
            "processing_jobs": 0,
            "stale_processing_jobs": 0,
            "failed_jobs": 0,
            "failed_jobs_last_24h": 0,
            "oldest_open_job_date": date(2025, 8, 31),
            "backlog_age_days": 0,
        },
        "reprocessing": {"active_reprocessing_keys": 0},
    }

    response = await client.get("/support/portfolios/P1/calculator-slos")

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["valuation"]["pending_jobs"] == 2


async def test_calculator_slos_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_calculator_slos.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/calculator-slos")

    assert response.status_code == 500
    assert "calculator slo snapshot" in response.json()["detail"].lower()


async def test_lineage_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage.return_value = {
        "portfolio_id": "P1",
        "security_id": "S1",
        "epoch": 2,
        "watermark_date": date(2025, 8, 1),
        "reprocessing_status": "CURRENT",
        "latest_position_history_date": date(2025, 8, 31),
        "latest_daily_snapshot_date": date(2025, 8, 31),
        "latest_valuation_job_date": date(2025, 8, 31),
        "latest_valuation_job_status": "DONE",
    }

    response = await client.get("/lineage/portfolios/P1/securities/S1")

    assert response.status_code == 200
    assert response.json()["security_id"] == "S1"


async def test_lineage_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage.side_effect = ValueError("Lineage state not found")

    response = await client.get("/lineage/portfolios/P1/securities/S404")

    assert response.status_code == 404
    assert "lineage state not found" in response.json()["detail"].lower()


async def test_lineage_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage.side_effect = RuntimeError("boom")

    response = await client.get("/lineage/portfolios/P1/securities/S500")

    assert response.status_code == 500
    assert "lineage response" in response.json()["detail"].lower()


async def test_get_operations_service_dependency_factory():
    db = AsyncMock(spec=AsyncSession)
    service = get_operations_service(db)

    assert isinstance(service, OperationsService)
    assert service.repo is not None


async def test_lineage_keys_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage_keys.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 50,
        "items": [
            {
                "security_id": "S1",
                "epoch": 2,
                "watermark_date": date(2025, 8, 1),
                "reprocessing_status": "CURRENT",
            }
        ],
    }

    response = await client.get("/lineage/portfolios/P1/keys?reprocessing_status=CURRENT")

    assert response.status_code == 200
    assert response.json()["items"][0]["security_id"] == "S1"


async def test_valuation_jobs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_valuation_jobs.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_type": "VALUATION",
                "business_date": date(2025, 8, 31),
                "status": "PENDING",
                "security_id": "S1",
                "epoch": 1,
                "attempt_count": 0,
                "failure_reason": None,
            }
        ],
    }

    response = await client.get("/support/portfolios/P1/valuation-jobs?status=PENDING")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_type"] == "VALUATION"


async def test_valuation_jobs_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_valuation_jobs.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/valuation-jobs?status=PENDING")

    assert response.status_code == 500
    assert "valuation jobs" in response.json()["detail"].lower()


async def test_aggregation_jobs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_aggregation_jobs.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_type": "AGGREGATION",
                "business_date": date(2025, 8, 31),
                "status": "PROCESSING",
                "security_id": None,
                "epoch": None,
                "attempt_count": 2,
                "failure_reason": "timed out once",
            }
        ],
    }

    response = await client.get("/support/portfolios/P1/aggregation-jobs?status=PROCESSING")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_type"] == "AGGREGATION"
    assert response.json()["items"][0]["attempt_count"] == 2
    assert response.json()["items"][0]["failure_reason"] == "timed out once"


async def test_aggregation_jobs_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_aggregation_jobs.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/aggregation-jobs?status=PROCESSING")

    assert response.status_code == 500
    assert "aggregation jobs" in response.json()["detail"].lower()


async def test_analytics_export_jobs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_analytics_export_jobs.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_id": "aexp_1234567890abcdef",
                "dataset_type": "portfolio_timeseries",
                "status": "FAILED",
                "created_at": "2026-03-13T10:15:00Z",
                "started_at": "2026-03-13T10:15:01Z",
                "completed_at": "2026-03-13T10:15:02Z",
                "result_row_count": None,
                "error_message": "Unexpected analytics export processing failure.",
            }
        ],
    }

    response = await client.get("/support/portfolios/P1/analytics-export-jobs?status_filter=FAILED")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_id"] == "aexp_1234567890abcdef"
    assert response.json()["items"][0]["dataset_type"] == "portfolio_timeseries"
    assert response.json()["items"][0]["status"] == "FAILED"


async def test_analytics_export_jobs_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_analytics_export_jobs.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/analytics-export-jobs?status_filter=FAILED")

    assert response.status_code == 500
    assert "analytics export jobs" in response.json()["detail"].lower()


async def test_lineage_keys_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage_keys.side_effect = RuntimeError("boom")

    response = await client.get("/lineage/portfolios/P1/keys?reprocessing_status=CURRENT")

    assert response.status_code == 500
    assert "lineage keys" in response.json()["detail"].lower()


async def test_support_overview_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_support_overview.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/overview")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_calculator_slos_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_calculator_slos.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/calculator-slos")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_valuation_jobs_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_valuation_jobs.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/valuation-jobs?status=PENDING")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_aggregation_jobs_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_aggregation_jobs.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/aggregation-jobs?status=PROCESSING")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_analytics_export_jobs_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_analytics_export_jobs.side_effect = ValueError("not found")

    response = await client.get(
        "/support/portfolios/P404/analytics-export-jobs?status_filter=FAILED"
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_lineage_keys_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage_keys.side_effect = ValueError("not found")

    response = await client.get("/lineage/portfolios/P404/keys?reprocessing_status=CURRENT")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
