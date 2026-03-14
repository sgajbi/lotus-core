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
        "stale_threshold_minutes": 30,
        "failed_window_hours": 48,
        "generated_at_utc": "2026-03-14T10:45:00Z",
        "active_reprocessing_keys": 1,
        "stale_reprocessing_keys": 1,
        "oldest_reprocessing_watermark_date": date(2025, 8, 20),
        "oldest_reprocessing_security_id": "S1",
        "oldest_reprocessing_epoch": 3,
        "oldest_reprocessing_updated_at": "2025-08-31T09:45:00Z",
        "reprocessing_backlog_age_days": 11,
        "pending_valuation_jobs": 2,
        "processing_valuation_jobs": 1,
        "stale_processing_valuation_jobs": 0,
        "failed_valuation_jobs": 0,
        "failed_valuation_jobs_within_window": 0,
        "oldest_pending_valuation_date": date(2025, 8, 30),
        "oldest_pending_valuation_job_id": 8801,
        "oldest_pending_valuation_security_id": "SEC-US-IBM",
        "oldest_pending_valuation_correlation_id": "corr-val-8801",
        "valuation_backlog_age_days": 1,
        "pending_aggregation_jobs": 0,
        "processing_aggregation_jobs": 0,
        "stale_processing_aggregation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "failed_aggregation_jobs_within_window": 0,
        "oldest_pending_aggregation_date": None,
        "oldest_pending_aggregation_job_id": None,
        "oldest_pending_aggregation_correlation_id": None,
        "aggregation_backlog_age_days": None,
        "pending_analytics_export_jobs": 2,
        "processing_analytics_export_jobs": 1,
        "stale_processing_analytics_export_jobs": 0,
        "failed_analytics_export_jobs": 1,
        "failed_analytics_export_jobs_within_window": 1,
        "oldest_pending_analytics_export_created_at": "2025-08-31T10:00:00Z",
        "oldest_pending_analytics_export_job_id": "aexp_0001",
        "oldest_pending_analytics_export_request_fingerprint": "pf-001:positions:csv",
        "analytics_export_backlog_age_minutes": 15,
        "latest_transaction_date": date(2025, 8, 31),
        "latest_booked_transaction_date": date(2025, 8, 31),
        "latest_position_snapshot_date": date(2025, 8, 31),
        "latest_booked_position_snapshot_date": date(2025, 8, 31),
        "position_snapshot_history_mismatch_count": 0,
        "controls_business_date": date(2025, 8, 31),
        "controls_stage_id": 701,
        "controls_last_source_event_type": "financial_reconciliation_completed",
        "controls_created_at": "2025-08-31T10:10:00Z",
        "controls_ready_emitted_at": "2025-08-31T10:15:00Z",
        "controls_epoch": 3,
        "controls_status": "COMPLETED",
        "controls_failure_reason": None,
        "controls_latest_reconciliation_run_id": "recon_1234567890abcdef",
        "controls_latest_reconciliation_type": "transaction_cashflow",
        "controls_latest_reconciliation_status": "COMPLETED",
        "controls_latest_reconciliation_correlation_id": "corr-recon-20250831-001",
        "controls_latest_reconciliation_requested_by": "pipeline_orchestrator_service",
        "controls_latest_reconciliation_dedupe_key": "recon:transaction_cashflow:P1:2025-08-31:3",
        "controls_latest_reconciliation_failure_reason": None,
        "controls_latest_reconciliation_total_findings": 2,
        "controls_latest_reconciliation_blocking_findings": 1,
        "controls_latest_blocking_finding_id": "rf_1234567890abcdef",
        "controls_latest_blocking_finding_type": "missing_cashflow",
        "controls_latest_blocking_finding_security_id": "SEC-US-IBM",
        "controls_latest_blocking_finding_transaction_id": "txn_0001",
        "controls_last_updated_at": "2025-08-31T10:16:00Z",
        "controls_blocking": False,
        "publish_allowed": True,
    }

    response = await client.get(
        "/support/portfolios/P1/overview?stale_threshold_minutes=30&failed_window_hours=48"
    )

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["failed_window_hours"] == 48
    assert response.json()["generated_at_utc"] == "2026-03-14T10:45:00Z"
    assert response.json()["oldest_reprocessing_security_id"] == "S1"
    assert response.json()["oldest_reprocessing_epoch"] == 3
    assert response.json()["oldest_reprocessing_updated_at"] == "2025-08-31T09:45:00Z"
    assert response.json()["oldest_pending_valuation_job_id"] == 8801
    assert response.json()["oldest_pending_valuation_security_id"] == "SEC-US-IBM"
    assert response.json()["oldest_pending_valuation_correlation_id"] == "corr-val-8801"
    assert response.json()["oldest_pending_analytics_export_job_id"] == "aexp_0001"
    assert response.json()["controls_stage_id"] == 701
    assert (
        response.json()["controls_last_source_event_type"]
        == "financial_reconciliation_completed"
    )
    assert response.json()["controls_created_at"] == "2025-08-31T10:10:00Z"
    assert response.json()["controls_ready_emitted_at"] == "2025-08-31T10:15:00Z"
    assert response.json()["controls_failure_reason"] is None
    assert response.json()["controls_latest_reconciliation_run_id"] == "recon_1234567890abcdef"
    assert response.json()["controls_latest_reconciliation_type"] == "transaction_cashflow"
    assert response.json()["controls_latest_reconciliation_status"] == "COMPLETED"
    assert (
        response.json()["controls_latest_reconciliation_correlation_id"]
        == "corr-recon-20250831-001"
    )
    assert (
        response.json()["controls_latest_reconciliation_requested_by"]
        == "pipeline_orchestrator_service"
    )
    assert (
        response.json()["controls_latest_reconciliation_dedupe_key"]
        == "recon:transaction_cashflow:P1:2025-08-31:3"
    )
    assert response.json()["controls_latest_reconciliation_failure_reason"] is None
    assert response.json()["controls_latest_reconciliation_total_findings"] == 2
    assert response.json()["controls_latest_reconciliation_blocking_findings"] == 1
    assert response.json()["controls_latest_blocking_finding_id"] == "rf_1234567890abcdef"
    assert response.json()["controls_latest_blocking_finding_type"] == "missing_cashflow"
    assert response.json()["controls_latest_blocking_finding_security_id"] == "SEC-US-IBM"
    assert response.json()["controls_latest_blocking_finding_transaction_id"] == "txn_0001"
    assert response.json()["controls_last_updated_at"] == "2025-08-31T10:16:00Z"
    assert response.json()["publish_allowed"] is True
    assert "X-Correlation-ID" in response.headers
    mock_service.get_support_overview.assert_awaited_once_with(
        portfolio_id="P1",
        stale_threshold_minutes=30,
        failed_window_hours=48,
    )


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
        "failed_window_hours": 48,
        "generated_at_utc": "2026-03-03T10:05:11Z",
        "valuation": {
            "pending_jobs": 2,
            "processing_jobs": 1,
            "stale_processing_jobs": 0,
            "failed_jobs": 0,
            "failed_jobs_within_window": 0,
            "oldest_open_job_date": date(2025, 8, 31),
            "oldest_open_job_id": 8801,
            "oldest_open_job_correlation_id": "corr-val-8801",
            "backlog_age_days": 0,
        },
        "aggregation": {
            "pending_jobs": 1,
            "processing_jobs": 0,
            "stale_processing_jobs": 0,
            "failed_jobs": 0,
            "failed_jobs_within_window": 0,
            "oldest_open_job_date": date(2025, 8, 31),
            "oldest_open_job_id": 4401,
            "oldest_open_job_correlation_id": "corr-agg-4401",
            "backlog_age_days": 0,
        },
        "reprocessing": {
            "active_reprocessing_keys": 0,
            "stale_reprocessing_keys": 0,
            "oldest_reprocessing_watermark_date": None,
            "oldest_reprocessing_security_id": None,
            "oldest_reprocessing_epoch": None,
            "oldest_reprocessing_updated_at": None,
            "backlog_age_days": None,
        },
    }

    response = await client.get(
        "/support/portfolios/P1/calculator-slos?stale_threshold_minutes=15&failed_window_hours=48"
    )

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["failed_window_hours"] == 48
    assert response.json()["valuation"]["pending_jobs"] == 2
    assert response.json()["valuation"]["oldest_open_job_id"] == 8801
    assert response.json()["valuation"]["oldest_open_job_correlation_id"] == "corr-val-8801"
    assert (
        response.json()["aggregation"]["oldest_open_job_correlation_id"] == "corr-agg-4401"
    )
    mock_service.get_calculator_slos.assert_awaited_once_with(
        portfolio_id="P1",
        stale_threshold_minutes=15,
        failed_window_hours=48,
    )


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
        "latest_valuation_job_id": 101,
        "latest_valuation_job_status": "DONE",
        "latest_valuation_job_correlation_id": "corr-val-101",
        "has_artifact_gap": False,
        "operational_state": "HEALTHY",
    }

    response = await client.get("/lineage/portfolios/P1/securities/S1")

    assert response.status_code == 200
    assert response.json()["security_id"] == "S1"
    assert response.json()["operational_state"] == "HEALTHY"


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
                "latest_position_history_date": date(2025, 8, 31),
                "latest_daily_snapshot_date": date(2025, 8, 30),
                "latest_valuation_job_date": date(2025, 8, 31),
                "latest_valuation_job_id": 101,
                "latest_valuation_job_status": "DONE",
                "latest_valuation_job_correlation_id": "corr-val-101",
                "has_artifact_gap": True,
                "operational_state": "ARTIFACT_GAP",
            }
        ],
    }

    response = await client.get("/lineage/portfolios/P1/keys?reprocessing_status=CURRENT")

    assert response.status_code == 200
    assert response.json()["items"][0]["security_id"] == "S1"
    assert response.json()["items"][0]["latest_valuation_job_id"] == 101
    assert response.json()["items"][0]["latest_valuation_job_status"] == "DONE"
    assert response.json()["items"][0]["latest_valuation_job_correlation_id"] == "corr-val-101"
    assert response.json()["items"][0]["operational_state"] == "ARTIFACT_GAP"


async def test_valuation_jobs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_valuation_jobs.return_value = {
        "portfolio_id": "P1",
        "stale_threshold_minutes": 30,
        "generated_at_utc": "2026-03-14T10:50:00Z",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_id": 101,
                "job_type": "VALUATION",
                "business_date": date(2025, 8, 31),
                "status": "PENDING",
                "security_id": "S1",
                "epoch": 1,
                "attempt_count": 0,
                "is_retrying": False,
                "correlation_id": "corr-val-101",
                "created_at": "2025-08-31T10:00:00Z",
                "updated_at": "2025-08-31T10:15:00Z",
                "is_stale_processing": False,
                "failure_reason": None,
                "is_terminal_failure": False,
                "operational_state": "PENDING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/valuation-jobs"
        "?job_id=101&business_date=2025-08-31&security_id=S1&correlation_id=corr-val-101"
        "&status=PENDING&stale_threshold_minutes=30"
    )

    assert response.status_code == 200
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["generated_at_utc"] == "2026-03-14T10:50:00Z"
    assert response.json()["items"][0]["job_type"] == "VALUATION"
    assert response.json()["items"][0]["is_stale_processing"] is False
    assert response.json()["items"][0]["is_retrying"] is False
    assert response.json()["items"][0]["operational_state"] == "PENDING"
    mock_service.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        job_id=101,
        business_date=date(2025, 8, 31),
        security_id="S1",
        correlation_id="corr-val-101",
        status="PENDING",
        stale_threshold_minutes=30,
    )


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
        "stale_threshold_minutes": 30,
        "generated_at_utc": "2026-03-14T10:50:00Z",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_id": 202,
                "job_type": "AGGREGATION",
                "business_date": date(2025, 8, 31),
                "status": "PROCESSING",
                "security_id": None,
                "epoch": None,
                "attempt_count": 2,
                "is_retrying": True,
                "correlation_id": "corr-agg-202",
                "created_at": "2025-08-31T09:45:00Z",
                "updated_at": "2025-08-31T10:00:00Z",
                "is_stale_processing": True,
                "failure_reason": "timed out once",
                "is_terminal_failure": False,
                "operational_state": "STALE_PROCESSING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/aggregation-jobs"
        "?job_id=202&business_date=2025-08-31"
        "&correlation_id=corr-agg-202&status=PROCESSING&stale_threshold_minutes=30"
    )

    assert response.status_code == 200
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["items"][0]["job_type"] == "AGGREGATION"
    assert response.json()["items"][0]["attempt_count"] == 2
    assert response.json()["items"][0]["is_stale_processing"] is True
    assert response.json()["items"][0]["is_retrying"] is True
    assert response.json()["items"][0]["failure_reason"] == "timed out once"
    assert response.json()["items"][0]["operational_state"] == "STALE_PROCESSING"
    mock_service.get_aggregation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        job_id=202,
        business_date=date(2025, 8, 31),
        correlation_id="corr-agg-202",
        status="PROCESSING",
        stale_threshold_minutes=30,
    )


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
        "stale_threshold_minutes": 30,
        "generated_at_utc": "2026-03-14T10:50:00Z",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_id": "aexp_1234567890abcdef",
                "request_fingerprint": "fp_portfolio_timeseries_pf001_20260313_v1",
                "dataset_type": "portfolio_timeseries",
                "status": "FAILED",
                "created_at": "2026-03-13T10:15:00Z",
                "started_at": "2026-03-13T10:15:01Z",
                "completed_at": "2026-03-13T10:15:02Z",
                "updated_at": "2026-03-13T10:15:02Z",
                "is_stale_running": False,
                "backlog_age_minutes": None,
                "result_row_count": None,
                "error_message": "Unexpected analytics export processing failure.",
                "is_terminal_failure": True,
                "operational_state": "FAILED",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/analytics-export-jobs"
        "?job_id=aexp_1234567890abcdef"
        "&request_fingerprint=fp_portfolio_timeseries_pf001_20260313_v1"
        "&status_filter=FAILED&stale_threshold_minutes=30"
    )

    assert response.status_code == 200
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["items"][0]["job_id"] == "aexp_1234567890abcdef"
    assert (
        response.json()["items"][0]["request_fingerprint"]
        == "fp_portfolio_timeseries_pf001_20260313_v1"
    )
    assert response.json()["items"][0]["dataset_type"] == "portfolio_timeseries"
    assert response.json()["items"][0]["status"] == "FAILED"
    assert response.json()["items"][0]["is_stale_running"] is False
    assert response.json()["items"][0]["is_terminal_failure"] is True
    assert response.json()["items"][0]["operational_state"] == "FAILED"
    mock_service.get_analytics_export_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        job_id="aexp_1234567890abcdef",
        request_fingerprint="fp_portfolio_timeseries_pf001_20260313_v1",
        status="FAILED",
        stale_threshold_minutes=30,
    )


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


async def test_reconciliation_runs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_runs.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "run_id": "recon_1234567890abcdef",
                "reconciliation_type": "transaction_cashflow",
                "status": "FAILED",
                "business_date": "2026-03-13",
                "epoch": 3,
                "started_at": "2026-03-13T10:15:00Z",
                "completed_at": "2026-03-13T10:15:09Z",
                "requested_by": "pipeline_orchestrator_service",
                "dedupe_key": "recon:transaction_cashflow:PF-001:2026-03-13:3",
                "correlation_id": "corr-recon-20260313-001",
                "failure_reason": "Tolerance exceeded for portfolio totals.",
                "is_terminal_failure": True,
                "is_blocking": True,
                "operational_state": "BLOCKING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/reconciliation-runs"
        "?run_id=recon_1234567890abcdef&correlation_id=corr-recon-20260313-001"
        "&reconciliation_type=transaction_cashflow&status_filter=FAILED"
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == "recon_1234567890abcdef"
    assert response.json()["items"][0]["status"] == "FAILED"
    assert response.json()["items"][0]["requested_by"] == "pipeline_orchestrator_service"
    assert (
        response.json()["items"][0]["dedupe_key"]
        == "recon:transaction_cashflow:PF-001:2026-03-13:3"
    )
    assert response.json()["items"][0]["correlation_id"] == "corr-recon-20260313-001"
    assert response.json()["items"][0]["is_terminal_failure"] is True
    assert response.json()["items"][0]["is_blocking"] is True
    assert response.json()["items"][0]["operational_state"] == "BLOCKING"
    mock_service.get_reconciliation_runs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        run_id="recon_1234567890abcdef",
        correlation_id="corr-recon-20260313-001",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
    )


async def test_reconciliation_runs_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_runs.side_effect = ValueError("not found")

    response = await client.get(
        "/support/portfolios/P404/reconciliation-runs?reconciliation_type=transaction_cashflow"
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_reconciliation_runs_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_runs.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/reconciliation-runs")

    assert response.status_code == 500
    assert "reconciliation runs" in response.json()["detail"].lower()


async def test_reconciliation_findings_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_findings.return_value = {
        "run_id": "recon_1234567890abcdef",
        "total": 1,
        "items": [
            {
                "finding_id": "rf_1234567890abcdef",
                "finding_type": "missing_cashflow",
                "severity": "ERROR",
                "security_id": "SEC-US-IBM",
                "transaction_id": "TXN-20260313-0042",
                "business_date": "2026-03-13",
                "epoch": 3,
                "created_at": "2026-03-13T10:15:09Z",
                "detail": {"expected_cashflow_count": 1, "observed_cashflow_count": 0},
                "is_blocking": True,
                "operational_state": "BLOCKING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/reconciliation-runs/recon_1234567890abcdef/findings"
        "?finding_id=rf_1234567890abcdef&limit=50"
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == "recon_1234567890abcdef"
    assert response.json()["items"][0]["finding_id"] == "rf_1234567890abcdef"
    assert response.json()["items"][0]["is_blocking"] is True
    assert response.json()["items"][0]["operational_state"] == "BLOCKING"
    mock_service.get_reconciliation_findings.assert_awaited_once_with(
        portfolio_id="P1",
        run_id="recon_1234567890abcdef",
        limit=50,
        finding_id="rf_1234567890abcdef",
    )


async def test_reconciliation_findings_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_findings.side_effect = ValueError(
        "Reconciliation run recon_404 not found for portfolio P404"
    )

    response = await client.get(
        "/support/portfolios/P404/reconciliation-runs/recon_404/findings?limit=50"
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_reconciliation_findings_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reconciliation_findings.side_effect = RuntimeError("boom")

    response = await client.get(
        "/support/portfolios/P1/reconciliation-runs/recon_123/findings?limit=50"
    )

    assert response.status_code == 500
    assert "reconciliation findings" in response.json()["detail"].lower()


async def test_portfolio_control_stages_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_control_stages.return_value = {
        "portfolio_id": "P1",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "stage_id": 701,
                "stage_name": "FINANCIAL_RECONCILIATION",
                "business_date": "2026-03-13",
                "epoch": 3,
                "status": "REQUIRES_REPLAY",
                "last_source_event_type": "financial_reconciliation_completed",
                "created_at": "2026-03-13T10:10:00Z",
                "ready_emitted_at": None,
                "updated_at": "2026-03-13T10:15:09Z",
                "is_blocking": True,
                "operational_state": "BLOCKING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/control-stages"
        "?stage_id=701&stage_name=FINANCIAL_RECONCILIATION&business_date=2026-03-13"
        "&status_filter=REQUIRES_REPLAY"
    )

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["items"][0]["stage_id"] == 701
    assert response.json()["items"][0]["stage_name"] == "FINANCIAL_RECONCILIATION"
    assert response.json()["items"][0]["created_at"] == "2026-03-13T10:10:00Z"
    assert response.json()["items"][0]["ready_emitted_at"] is None
    assert response.json()["items"][0]["is_blocking"] is True
    assert response.json()["items"][0]["operational_state"] == "BLOCKING"
    mock_service.get_portfolio_control_stages.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )


async def test_portfolio_control_stages_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_control_stages.side_effect = ValueError("not found")

    response = await client.get(
        "/support/portfolios/P404/control-stages?stage_name=FINANCIAL_RECONCILIATION"
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_portfolio_control_stages_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_control_stages.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/control-stages")

    assert response.status_code == 500
    assert "portfolio control stages" in response.json()["detail"].lower()


async def test_reprocessing_keys_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_keys.return_value = {
        "portfolio_id": "P1",
        "stale_threshold_minutes": 30,
        "generated_at_utc": "2026-03-14T10:50:00Z",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "security_id": "SEC-US-IBM",
                "epoch": 3,
                "watermark_date": "2026-03-10",
                "status": "REPROCESSING",
                "created_at": "2026-03-13T10:05:00Z",
                "updated_at": "2026-03-13T10:15:09Z",
                "is_stale_reprocessing": False,
                "operational_state": "REPROCESSING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/reprocessing-keys"
        "?status_filter=REPROCESSING&security_id=SEC-US-IBM"
        "&watermark_date=2026-03-10&stale_threshold_minutes=30"
    )

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["items"][0]["security_id"] == "SEC-US-IBM"
    assert response.json()["items"][0]["created_at"] == "2026-03-13T10:05:00Z"
    assert response.json()["items"][0]["is_stale_reprocessing"] is False
    assert response.json()["items"][0]["operational_state"] == "REPROCESSING"
    mock_service.get_reprocessing_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        watermark_date=date(2026, 3, 10),
        stale_threshold_minutes=30,
    )


async def test_reprocessing_keys_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_keys.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/reprocessing-keys")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_reprocessing_keys_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_keys.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/reprocessing-keys")

    assert response.status_code == 500
    assert "reprocessing keys" in response.json()["detail"].lower()


async def test_reprocessing_jobs_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_jobs.return_value = {
        "portfolio_id": "P1",
        "stale_threshold_minutes": 30,
        "generated_at_utc": "2026-03-14T10:50:00Z",
        "total": 1,
        "skip": 0,
        "limit": 100,
        "items": [
            {
                "job_id": 303,
                "job_type": "RESET_WATERMARKS",
                "business_date": "2026-03-10",
                "status": "PROCESSING",
                "security_id": "SEC-US-IBM",
                "epoch": None,
                "attempt_count": 2,
                "is_retrying": True,
                "correlation_id": "corr-replay-303",
                "created_at": "2025-08-31T09:50:00Z",
                "updated_at": "2026-03-13T10:15:09Z",
                "is_stale_processing": False,
                "failure_reason": "timed out once",
                "is_terminal_failure": False,
                "operational_state": "PROCESSING",
            }
        ],
    }

    response = await client.get(
        "/support/portfolios/P1/reprocessing-jobs"
        "?job_id=303&correlation_id=corr-replay-303"
        "&status_filter=PROCESSING&security_id=SEC-US-IBM&stale_threshold_minutes=30"
    )

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"
    assert response.json()["stale_threshold_minutes"] == 30
    assert response.json()["items"][0]["job_type"] == "RESET_WATERMARKS"
    assert response.json()["items"][0]["security_id"] == "SEC-US-IBM"
    mock_service.get_reprocessing_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=100,
        job_id=303,
        correlation_id="corr-replay-303",
        status="PROCESSING",
        security_id="SEC-US-IBM",
        stale_threshold_minutes=30,
    )


async def test_reprocessing_jobs_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_jobs.side_effect = ValueError("not found")

    response = await client.get("/support/portfolios/P404/reprocessing-jobs")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_reprocessing_jobs_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_reprocessing_jobs.side_effect = RuntimeError("boom")

    response = await client.get("/support/portfolios/P1/reprocessing-jobs")

    assert response.status_code == 500
    assert "reprocessing jobs" in response.json()["detail"].lower()


async def test_lineage_keys_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_lineage_keys.side_effect = ValueError("not found")

    response = await client.get("/lineage/portfolios/P404/keys?reprocessing_status=CURRENT")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
