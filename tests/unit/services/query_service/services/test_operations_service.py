from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.operations_repository import (
    ExportJobHealthSummary,
    JobHealthSummary,
)
from src.services.query_service.app.services.operations_service import OperationsService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_ops_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.portfolio_exists.return_value = True
    return repo


@pytest.fixture
def service(mock_ops_repo: AsyncMock) -> OperationsService:
    with patch(
        "src.services.query_service.app.services.operations_service.OperationsRepository",
        return_value=mock_ops_repo,
    ):
        return OperationsService(AsyncMock(spec=AsyncSession))


async def test_get_support_overview(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_current_portfolio_epoch.return_value = 2
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 1
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=4,
        processing_jobs=2,
        stale_processing_jobs=1,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=date(2025, 8, 20),
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=1,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=2,
        running_jobs=1,
        stale_running_jobs=0,
        failed_jobs=1,
        failed_jobs_last_hours=1,
        oldest_open_job_created_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 9, 2)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = type(
        "ControlStageStub",
        (),
        {"business_date": date(2025, 8, 30), "epoch": 2, "status": "COMPLETED"},
    )()

    response = await service.get_support_overview("P1")

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2025, 8, 30)
    assert response.current_epoch == 2
    assert response.active_reprocessing_keys == 1
    assert response.pending_valuation_jobs == 4
    assert response.processing_valuation_jobs == 2
    assert response.stale_processing_valuation_jobs == 1
    assert response.failed_valuation_jobs == 0
    assert response.oldest_pending_valuation_date == date(2025, 8, 20)
    assert response.valuation_backlog_age_days == 10
    assert response.pending_aggregation_jobs == 1
    assert response.processing_aggregation_jobs == 0
    assert response.stale_processing_aggregation_jobs == 0
    assert response.failed_aggregation_jobs == 0
    assert response.oldest_pending_aggregation_date is None
    assert response.aggregation_backlog_age_days is None
    assert response.pending_analytics_export_jobs == 2
    assert response.processing_analytics_export_jobs == 1
    assert response.stale_processing_analytics_export_jobs == 0
    assert response.failed_analytics_export_jobs == 1
    assert response.oldest_pending_analytics_export_created_at == datetime(
        2025, 8, 30, 10, 0, tzinfo=timezone.utc
    )
    assert response.analytics_export_backlog_age_minutes is not None
    assert response.latest_transaction_date == date(2025, 9, 2)
    assert response.latest_booked_transaction_date == date(2025, 8, 30)
    assert response.latest_position_snapshot_date == date(2025, 8, 30)
    assert response.latest_booked_position_snapshot_date == date(2025, 8, 30)
    assert response.position_snapshot_history_mismatch_count == 0
    assert response.controls_business_date == date(2025, 8, 30)
    assert response.controls_epoch == 2
    assert response.controls_status == "COMPLETED"
    assert response.controls_blocking is False
    assert response.publish_allowed is True


async def test_get_lineage_raises_when_state_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_position_state.return_value = None

    with pytest.raises(ValueError, match="Lineage state not found"):
        await service.get_lineage("P1", "S1")


async def test_get_lineage_success(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_position_state.return_value = type(
        "PositionStateStub",
        (),
        {"epoch": 3, "watermark_date": date(2025, 8, 1), "status": "CURRENT"},
    )()
    mock_ops_repo.get_latest_position_history_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_daily_snapshot_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_valuation_job.return_value = type(
        "ValuationJobStub",
        (),
        {
            "id": 101,
            "valuation_date": date(2025, 8, 31),
            "status": "DONE",
            "correlation_id": "corr-val-101",
        },
    )()

    response = await service.get_lineage("P1", "S1")

    assert response.portfolio_id == "P1"
    assert response.security_id == "S1"
    assert response.epoch == 3
    assert response.latest_position_history_date == date(2025, 8, 31)
    assert response.latest_daily_snapshot_date == date(2025, 8, 31)
    assert response.latest_valuation_job_id == 101
    assert response.latest_valuation_job_status == "DONE"
    assert response.latest_valuation_job_correlation_id == "corr-val-101"
    assert response.has_artifact_gap is False
    assert response.operational_state == "HEALTHY"


async def test_get_lineage_valuation_blocked(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_position_state.return_value = type(
        "PositionStateStub",
        (),
        {"epoch": 3, "watermark_date": date(2025, 8, 1), "status": "CURRENT"},
    )()
    mock_ops_repo.get_latest_position_history_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_daily_snapshot_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_valuation_job.return_value = type(
        "ValuationJobStub",
        (),
        {
            "id": 102,
            "valuation_date": date(2025, 8, 31),
            "status": "FAILED",
            "correlation_id": "corr-val-102",
        },
    )()

    response = await service.get_lineage("P1", "S1")

    assert response.has_artifact_gap is True
    assert response.operational_state == "VALUATION_BLOCKED"


async def test_get_lineage_keys(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_lineage_keys_count.return_value = 1
    mock_ops_repo.get_lineage_keys.return_value = [
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
        }
    ]

    response = await service.get_lineage_keys(
        "P1", skip=0, limit=10, reprocessing_status="CURRENT", security_id=None
    )

    assert response.total == 1
    assert response.items[0].security_id == "S1"
    assert response.items[0].reprocessing_status == "CURRENT"
    assert response.items[0].latest_position_history_date == date(2025, 8, 31)
    assert response.items[0].latest_daily_snapshot_date == date(2025, 8, 30)
    assert response.items[0].latest_valuation_job_date == date(2025, 8, 31)
    assert response.items[0].latest_valuation_job_id == 101
    assert response.items[0].latest_valuation_job_status == "DONE"
    assert response.items[0].latest_valuation_job_correlation_id == "corr-val-101"
    assert response.items[0].has_artifact_gap is True
    assert response.items[0].operational_state == "ARTIFACT_GAP"


async def test_build_lineage_key_record_healthy_state(service: OperationsService):
    record = service._build_lineage_key_record(
        {
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
        }
    )

    assert record.has_artifact_gap is False
    assert record.operational_state == "HEALTHY"


async def test_build_lineage_key_record_replaying_state(service: OperationsService):
    record = service._build_lineage_key_record(
        {
            "security_id": "S1",
            "epoch": 2,
            "watermark_date": date(2025, 8, 1),
            "reprocessing_status": "REPROCESSING",
            "latest_position_history_date": date(2025, 8, 31),
            "latest_daily_snapshot_date": date(2025, 8, 30),
            "latest_valuation_job_date": date(2025, 8, 31),
            "latest_valuation_job_id": 101,
            "latest_valuation_job_status": "DONE",
            "latest_valuation_job_correlation_id": "corr-val-101",
        }
    )

    assert record.has_artifact_gap is True
    assert record.operational_state == "REPLAYING"


async def test_build_lineage_key_record_valuation_blocked_state(service: OperationsService):
    record = service._build_lineage_key_record(
        {
            "security_id": "S1",
            "epoch": 2,
            "watermark_date": date(2025, 8, 1),
            "reprocessing_status": "CURRENT",
            "latest_position_history_date": date(2025, 8, 31),
            "latest_daily_snapshot_date": date(2025, 8, 31),
            "latest_valuation_job_date": date(2025, 8, 31),
            "latest_valuation_job_id": 102,
            "latest_valuation_job_status": "FAILED",
            "latest_valuation_job_correlation_id": "corr-val-102",
        }
    )

    assert record.has_artifact_gap is True
    assert record.operational_state == "VALUATION_BLOCKED"


async def test_get_valuation_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2025, 8, 31, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2025, 8, 31, 10, 15, tzinfo=timezone.utc)
    mock_ops_repo.get_valuation_jobs_count.return_value = 1
    mock_ops_repo.get_valuation_jobs.return_value = [
        type(
            "ValuationJobStub",
            (),
            {
                "id": 101,
                "security_id": "S1",
                "valuation_date": date(2025, 8, 31),
                "status": "PENDING",
                "epoch": 1,
                "attempt_count": 0,
                "correlation_id": "corr-val-101",
                "created_at": created_at,
                "updated_at": updated_at,
                "failure_reason": None,
            },
        )()
    ]

    response = await service.get_valuation_jobs("P1", skip=0, limit=20, status="PENDING")

    assert response.total == 1
    assert response.items[0].job_id == 101
    assert response.items[0].job_type == "VALUATION"
    assert response.items[0].security_id == "S1"
    assert response.items[0].business_date == date(2025, 8, 31)
    assert response.items[0].created_at == created_at
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_stale_processing is False
    assert response.items[0].is_retrying is False
    assert response.items[0].correlation_id == "corr-val-101"
    assert response.items[0].is_terminal_failure is False
    assert response.items[0].operational_state == "PENDING"
    mock_ops_repo.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1", skip=0, limit=20, status="PENDING", stale_minutes=15
    )


async def test_get_aggregation_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2025, 8, 31, 9, 45, tzinfo=timezone.utc)
    updated_at = datetime(2025, 8, 31, 10, 0, tzinfo=timezone.utc)
    mock_ops_repo.get_aggregation_jobs_count.return_value = 1
    mock_ops_repo.get_aggregation_jobs.return_value = [
        type(
            "AggregationJobStub",
            (),
            {
                "id": 202,
                "aggregation_date": date(2025, 8, 31),
                "status": "PROCESSING",
                "attempt_count": 2,
                "correlation_id": "corr-agg-202",
                "created_at": created_at,
                "updated_at": updated_at,
                "failure_reason": "timed out once",
            },
        )()
    ]

    response = await service.get_aggregation_jobs("P1", skip=0, limit=20, status="PROCESSING")

    assert response.total == 1
    assert response.items[0].job_id == 202
    assert response.items[0].job_type == "AGGREGATION"
    assert response.items[0].business_date == date(2025, 8, 31)
    assert response.items[0].attempt_count == 2
    assert response.items[0].created_at == created_at
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_stale_processing is True
    assert response.items[0].is_retrying is True
    assert response.items[0].correlation_id == "corr-agg-202"
    assert response.items[0].failure_reason == "timed out once"
    assert response.items[0].is_terminal_failure is False
    assert response.items[0].operational_state == "STALE_PROCESSING"
    mock_ops_repo.get_aggregation_jobs.assert_awaited_once_with(
        portfolio_id="P1", skip=0, limit=20, status="PROCESSING", stale_minutes=15
    )


async def test_get_reprocessing_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2025, 8, 31, 9, 50, tzinfo=timezone.utc)
    updated_at = datetime(2025, 8, 31, 10, 0, tzinfo=timezone.utc)
    mock_ops_repo.get_reprocessing_jobs_count.return_value = 1
    mock_ops_repo.get_reprocessing_jobs.return_value = [
        type(
            "ReprocessingJobStub",
            (),
            {
                "id": 303,
                "job_type": "RESET_WATERMARKS",
                "business_date": "2025-08-15",
                "status": "PROCESSING",
                "security_id": "S1",
                "attempt_count": 2,
                "correlation_id": "corr-replay-303",
                "created_at": created_at,
                "updated_at": updated_at,
                "failure_reason": "timed out once",
            },
        )()
    ]

    response = await service.get_reprocessing_jobs(
        "P1", skip=0, limit=20, status="PROCESSING", security_id="S1"
    )

    assert response.total == 1
    assert response.items[0].job_id == 303
    assert response.items[0].job_type == "RESET_WATERMARKS"
    assert response.items[0].security_id == "S1"
    assert response.items[0].business_date == date(2025, 8, 15)
    assert response.items[0].attempt_count == 2
    assert response.items[0].created_at == created_at
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_retrying is True
    assert response.items[0].correlation_id == "corr-replay-303"
    assert response.items[0].is_stale_processing is True
    assert response.items[0].failure_reason == "timed out once"
    assert response.items[0].is_terminal_failure is False
    assert response.items[0].operational_state == "STALE_PROCESSING"
    mock_ops_repo.get_reprocessing_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        security_id="S1",
        stale_minutes=15,
    )


async def test_support_job_stale_flag_only_marks_old_processing():
    updated_at = datetime(2025, 8, 31, 10, 0, tzinfo=timezone.utc)

    assert (
        OperationsService._is_support_job_stale(
            "PROCESSING",
            updated_at,
            now=datetime(2025, 8, 31, 10, 20, tzinfo=timezone.utc),
        )
        is True
    )
    assert (
        OperationsService._is_support_job_stale(
            "PROCESSING",
            updated_at,
            now=datetime(2025, 8, 31, 10, 10, tzinfo=timezone.utc),
        )
        is False
    )
    assert (
        OperationsService._is_support_job_stale(
            "FAILED",
            updated_at,
            now=datetime(2025, 8, 31, 11, 0, tzinfo=timezone.utc),
        )
        is False
    )


async def test_get_analytics_export_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2026, 3, 13, 10, 15, tzinfo=timezone.utc)
    started_at = datetime(2026, 3, 13, 10, 16, tzinfo=timezone.utc)
    completed_at = datetime(2026, 3, 13, 10, 18, tzinfo=timezone.utc)
    updated_at = datetime(2026, 3, 13, 10, 18, tzinfo=timezone.utc)
    mock_ops_repo.get_analytics_export_jobs_count.return_value = 1
    mock_ops_repo.get_analytics_export_jobs.return_value = [
        type(
            "AnalyticsExportJobStub",
            (),
            {
                "job_id": "aexp_1234567890abcdef",
                "dataset_type": "portfolio_timeseries",
                "status": "FAILED",
                "created_at": created_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "updated_at": updated_at,
                "result_row_count": None,
                "error_message": "Unexpected analytics export processing failure.",
            },
        )()
    ]

    response = await service.get_analytics_export_jobs("P1", skip=0, limit=20, status="FAILED")

    assert response.total == 1
    assert response.items[0].job_id == "aexp_1234567890abcdef"
    assert response.items[0].dataset_type == "portfolio_timeseries"
    assert response.items[0].status == "FAILED"
    assert response.items[0].created_at == created_at
    assert response.items[0].started_at == started_at
    assert response.items[0].completed_at == completed_at
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_stale_running is False
    assert response.items[0].backlog_age_minutes is None
    assert response.items[0].error_message == "Unexpected analytics export processing failure."
    assert response.items[0].is_terminal_failure is True
    assert response.items[0].operational_state == "FAILED"
    mock_ops_repo.get_analytics_export_jobs.assert_awaited_once_with(
        portfolio_id="P1", skip=0, limit=20, status="FAILED", stale_minutes=15
    )


async def test_analytics_export_job_flags_running_staleness_and_backlog_age():
    created_at = datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 3, 13, 10, 5, tzinfo=timezone.utc)
    now = datetime(2026, 3, 13, 10, 30, tzinfo=timezone.utc)

    assert OperationsService._is_analytics_export_job_stale("running", updated_at, now=now) is True
    assert (
        OperationsService._get_analytics_export_backlog_age_minutes("running", created_at, now=now)
        == 30
    )
    assert (
        OperationsService._get_analytics_export_backlog_age_minutes("failed", created_at, now=now)
        is None
    )
    assert (
        OperationsService._get_analytics_export_operational_state("running", updated_at)
        == "STALE_RUNNING"
    )


async def test_get_reconciliation_runs(service: OperationsService, mock_ops_repo: AsyncMock):
    started_at = datetime(2026, 3, 13, 10, 15, tzinfo=timezone.utc)
    completed_at = datetime(2026, 3, 13, 10, 18, tzinfo=timezone.utc)
    mock_ops_repo.get_reconciliation_runs_count.return_value = 1
    mock_ops_repo.get_reconciliation_runs.return_value = [
        type(
            "ReconciliationRunStub",
            (),
            {
                "run_id": "recon_1234567890abcdef",
                "reconciliation_type": "transaction_cashflow",
                "status": "FAILED",
                "business_date": date(2026, 3, 13),
                "epoch": 3,
                "started_at": started_at,
                "completed_at": completed_at,
                "correlation_id": "corr-recon-20260313-001",
                "failure_reason": "Tolerance exceeded for portfolio totals.",
            },
        )()
    ]

    response = await service.get_reconciliation_runs(
        "P1",
        skip=0,
        limit=20,
        reconciliation_type="transaction_cashflow",
        status="FAILED",
    )

    assert response.total == 1
    assert response.items[0].run_id == "recon_1234567890abcdef"
    assert response.items[0].reconciliation_type == "transaction_cashflow"
    assert response.items[0].status == "FAILED"
    assert response.items[0].correlation_id == "corr-recon-20260313-001"
    assert response.items[0].failure_reason == "Tolerance exceeded for portfolio totals."
    assert response.items[0].is_terminal_failure is True
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"


async def test_support_job_retrying_only_for_active_retry_states():
    assert OperationsService._is_support_job_retrying("PENDING", 1) is True
    assert OperationsService._is_support_job_retrying("PROCESSING", 2) is True
    assert OperationsService._is_support_job_retrying("FAILED", 3) is False
    assert OperationsService._is_support_job_retrying("PENDING", 0) is False


async def test_support_job_operational_state_branches():
    updated_at = datetime.now(timezone.utc)
    assert OperationsService._get_support_job_operational_state("FAILED", updated_at) == "FAILED"
    assert OperationsService._get_support_job_operational_state("PENDING", updated_at) == "PENDING"
    assert OperationsService._get_support_job_operational_state("DONE", updated_at) == "COMPLETED"


async def test_analytics_export_operational_state_branches():
    updated_at = datetime.now(timezone.utc)
    assert OperationsService._normalize_analytics_export_status(None) is None
    assert (
        OperationsService._get_analytics_export_operational_state("FAILED", updated_at)
        == "FAILED"
    )
    assert (
        OperationsService._get_analytics_export_operational_state("accepted", updated_at)
        == "ACCEPTED"
    )
    assert (
        OperationsService._get_analytics_export_operational_state("completed", updated_at)
        == "COMPLETED"
    )


async def test_reconciliation_and_reprocessing_operational_state_branches():
    updated_at = datetime.now(timezone.utc)

    assert OperationsService._get_reconciliation_operational_state("REQUIRES_REPLAY") == "BLOCKING"
    assert OperationsService._get_reconciliation_operational_state("RUNNING") == "RUNNING"
    assert OperationsService._get_reconciliation_operational_state("COMPLETED") == "COMPLETED"
    assert OperationsService._get_portfolio_control_stage_operational_state("FAILED") == "BLOCKING"
    assert (
        OperationsService._get_portfolio_control_stage_operational_state("COMPLETED")
        == "COMPLETED"
    )
    assert (
        OperationsService._get_reprocessing_key_operational_state("CURRENT", updated_at)
        == "CURRENT"
    )
    assert OperationsService._is_reconciliation_finding_blocking("ERROR") is True
    assert OperationsService._is_reconciliation_finding_blocking("WARNING") is False
    assert (
        OperationsService._get_reconciliation_finding_operational_state("ERROR") == "BLOCKING"
    )
    assert (
        OperationsService._get_reconciliation_finding_operational_state("INFO")
        == "NON_BLOCKING"
    )


async def test_stale_detection_helpers_cover_remaining_branches():
    now = datetime(2026, 3, 13, 10, 30, tzinfo=timezone.utc)
    stale = datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)
    fresh = datetime(2026, 3, 13, 10, 20, tzinfo=timezone.utc)
    current_fresh = datetime.now(timezone.utc)

    assert OperationsService._is_support_job_stale("PROCESSING", stale, now=now) is True
    assert OperationsService._is_support_job_stale("PROCESSING", fresh, now=now) is False
    assert OperationsService._is_support_job_stale("FAILED", stale, now=now) is False
    assert OperationsService._is_analytics_export_job_stale("running", stale, now=now) is True
    assert OperationsService._is_analytics_export_job_stale("running", fresh, now=now) is False
    assert OperationsService._is_reprocessing_key_stale("REPROCESSING", stale, now=now) is True
    assert (
        OperationsService._get_support_job_operational_state("PROCESSING", current_fresh)
        == "PROCESSING"
    )
    assert (
        OperationsService._get_analytics_export_operational_state("running", current_fresh)
        == "RUNNING"
    )
    assert (
        OperationsService._get_reprocessing_key_operational_state("REPROCESSING", current_fresh)
        == "REPROCESSING"
    )


async def test_get_reconciliation_findings(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2026, 3, 13, 10, 18, tzinfo=timezone.utc)
    mock_ops_repo.get_reconciliation_run.return_value = type(
        "ReconciliationRunStub",
        (),
        {"run_id": "recon_1234567890abcdef"},
    )()
    mock_ops_repo.get_reconciliation_findings_count.return_value = 7
    mock_ops_repo.get_reconciliation_findings.return_value = [
        type(
            "ReconciliationFindingStub",
            (),
            {
                "finding_id": "rf_1234567890abcdef",
                "finding_type": "missing_cashflow",
                "severity": "ERROR",
                "security_id": "SEC-US-IBM",
                "transaction_id": "TXN-20260313-0042",
                "business_date": date(2026, 3, 13),
                "epoch": 3,
                "created_at": created_at,
                "detail": {"expected_cashflow_count": 1, "observed_cashflow_count": 0},
            },
        )()
    ]

    response = await service.get_reconciliation_findings(
        portfolio_id="P1",
        run_id="recon_1234567890abcdef",
        limit=50,
    )

    assert response.run_id == "recon_1234567890abcdef"
    assert response.total == 7
    assert response.items[0].finding_id == "rf_1234567890abcdef"
    assert response.items[0].severity == "ERROR"
    assert response.items[0].detail == {"expected_cashflow_count": 1, "observed_cashflow_count": 0}
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"


async def test_get_reconciliation_findings_raises_when_run_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_reconciliation_run.return_value = None

    with pytest.raises(
        ValueError,
        match="Reconciliation run recon_1234567890abcdef not found for portfolio P1",
    ):
        await service.get_reconciliation_findings(
            portfolio_id="P1",
            run_id="recon_1234567890abcdef",
            limit=50,
        )


async def test_get_portfolio_control_stages(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2026, 3, 13, 10, 10, tzinfo=timezone.utc)
    updated_at = datetime(2026, 3, 13, 10, 15, tzinfo=timezone.utc)
    mock_ops_repo.get_portfolio_control_stages_count.return_value = 1
    mock_ops_repo.get_portfolio_control_stages.return_value = [
        type(
            "PipelineStageStub",
            (),
            {
                "id": 701,
                "stage_name": "FINANCIAL_RECONCILIATION",
                "business_date": date(2026, 3, 13),
                "epoch": 3,
                "status": "REQUIRES_REPLAY",
                "last_source_event_type": "financial_reconciliation_completed",
                "created_at": created_at,
                "ready_emitted_at": None,
                "updated_at": updated_at,
            },
        )()
    ]

    response = await service.get_portfolio_control_stages(
        portfolio_id="P1",
        skip=0,
        limit=50,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )

    assert response.portfolio_id == "P1"
    assert response.total == 1
    assert response.items[0].stage_id == 701
    assert response.items[0].stage_name == "FINANCIAL_RECONCILIATION"
    assert response.items[0].business_date == date(2026, 3, 13)
    assert response.items[0].epoch == 3
    assert response.items[0].status == "REQUIRES_REPLAY"
    assert response.items[0].last_source_event_type == "financial_reconciliation_completed"
    assert response.items[0].created_at == created_at
    assert response.items[0].ready_emitted_at is None
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"
    mock_ops_repo.get_portfolio_control_stages.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=50,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )


async def test_get_reprocessing_keys(service: OperationsService, mock_ops_repo: AsyncMock):
    updated_at = datetime.now(timezone.utc)
    mock_ops_repo.get_reprocessing_keys_count.return_value = 1
    mock_ops_repo.get_reprocessing_keys.return_value = [
        type(
            "PositionStateStub",
            (),
            {
                "security_id": "SEC-US-IBM",
                "epoch": 3,
                "watermark_date": date(2026, 3, 10),
                "status": "REPROCESSING",
                "updated_at": updated_at,
            },
        )()
    ]

    response = await service.get_reprocessing_keys(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
    )

    assert response.portfolio_id == "P1"
    assert response.total == 1
    assert response.items[0].security_id == "SEC-US-IBM"
    assert response.items[0].epoch == 3
    assert response.items[0].watermark_date == date(2026, 3, 10)
    assert response.items[0].status == "REPROCESSING"
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_stale_reprocessing is False
    assert response.items[0].operational_state == "REPROCESSING"
    mock_ops_repo.get_reprocessing_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        stale_minutes=15,
    )


async def test_get_support_overview_raises_when_portfolio_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.portfolio_exists.return_value = False

    with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
        await service.get_support_overview("P404")


async def test_get_support_overview_without_business_date(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = None
    mock_ops_repo.get_current_portfolio_epoch.return_value = 1
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 0
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=0,
        running_jobs=0,
        stale_running_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_created_at=None,
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 31)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = None

    response = await service.get_support_overview("P1")

    assert response.business_date is None
    assert response.valuation_backlog_age_days is None
    assert response.aggregation_backlog_age_days is None
    assert response.pending_analytics_export_jobs == 0
    assert response.processing_analytics_export_jobs == 0
    assert response.stale_processing_analytics_export_jobs == 0
    assert response.failed_analytics_export_jobs == 0
    assert response.oldest_pending_analytics_export_created_at is None
    assert response.analytics_export_backlog_age_minutes is None
    assert response.latest_booked_transaction_date is None
    assert response.latest_booked_position_snapshot_date is None
    assert response.controls_status is None
    assert response.controls_blocking is False
    assert response.publish_allowed is True
    mock_ops_repo.get_latest_transaction_date_as_of.assert_not_awaited()
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.assert_not_awaited()


async def test_get_support_overview_marks_publish_blocked_when_controls_require_replay(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_current_portfolio_epoch.return_value = 2
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 0
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=0,
        running_jobs=0,
        stale_running_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_created_at=None,
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = type(
        "ControlStageStub",
        (),
        {"business_date": date(2025, 8, 30), "epoch": 2, "status": "REQUIRES_REPLAY"},
    )()

    response = await service.get_support_overview("P1")

    assert response.controls_status == "REQUIRES_REPLAY"
    assert response.controls_blocking is True
    assert response.publish_allowed is False


async def test_get_calculator_slos(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 2
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=7,
        processing_jobs=3,
        stale_processing_jobs=1,
        failed_jobs=4,
        failed_jobs_last_hours=2,
        oldest_open_job_date=date(2025, 8, 20),
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=5,
        processing_jobs=2,
        stale_processing_jobs=1,
        failed_jobs=1,
        failed_jobs_last_hours=1,
        oldest_open_job_date=date(2025, 8, 25),
    )

    response = await service.get_calculator_slos("P1", stale_threshold_minutes=15)

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2025, 8, 30)
    assert response.stale_threshold_minutes == 15
    assert response.valuation.pending_jobs == 7
    assert response.valuation.failed_jobs == 4
    assert response.valuation.failed_jobs_last_24h == 2
    assert response.valuation.backlog_age_days == 10
    assert response.aggregation.pending_jobs == 5
    assert response.aggregation.failed_jobs == 1
    assert response.aggregation.backlog_age_days == 5
    assert response.reprocessing.active_reprocessing_keys == 2
