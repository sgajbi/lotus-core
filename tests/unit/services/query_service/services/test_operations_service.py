from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.operations_repository import (
    ExportJobHealthSummary,
    JobHealthSummary,
    ReconciliationFindingSummary,
    ReprocessingHealthSummary,
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
    mock_ops_repo.get_reprocessing_health_summary.return_value = ReprocessingHealthSummary(
        active_keys=1,
        stale_reprocessing_keys=1,
        oldest_reprocessing_watermark_date=date(2025, 8, 18),
        oldest_reprocessing_security_id="S1",
        oldest_reprocessing_epoch=3,
        oldest_reprocessing_updated_at=datetime(2025, 8, 30, 9, 45, tzinfo=timezone.utc),
    )
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=4,
        processing_jobs=2,
        stale_processing_jobs=1,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=date(2025, 8, 20),
        oldest_open_job_id=8801,
        oldest_open_job_correlation_id="corr-val-8801",
        oldest_open_security_id="SEC-US-IBM",
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=1,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=2,
        running_jobs=1,
        stale_running_jobs=0,
        failed_jobs=1,
        failed_jobs_last_hours=1,
        oldest_open_job_created_at=datetime(2025, 8, 30, 10, 0, tzinfo=timezone.utc),
        oldest_open_job_id="aexp_0001",
        oldest_open_request_fingerprint="pf-001:positions:csv",
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 9, 2)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = type(
        "ControlStageStub",
        (),
        {
            "id": 701,
            "business_date": date(2025, 8, 30),
            "epoch": 2,
            "status": "COMPLETED",
            "failure_reason": None,
            "last_source_event_type": "financial_reconciliation_completed",
            "created_at": datetime(2025, 8, 30, 10, 10, tzinfo=timezone.utc),
            "ready_emitted_at": datetime(2025, 8, 30, 10, 14, tzinfo=timezone.utc),
            "updated_at": datetime(2025, 8, 30, 10, 15, tzinfo=timezone.utc),
        },
    )()
    mock_ops_repo.get_latest_reconciliation_run_for_portfolio_day.return_value = type(
        "ReconciliationRunStub",
        (),
        {
            "run_id": "recon_1234567890abcdef",
            "reconciliation_type": "transaction_cashflow",
            "status": "COMPLETED",
            "correlation_id": "corr-recon-20250830-001",
            "requested_by": "pipeline_orchestrator_service",
            "dedupe_key": "recon:transaction_cashflow:P1:2025-08-30:2",
            "failure_reason": None,
        },
    )()
    mock_ops_repo.get_reconciliation_finding_summary.return_value = ReconciliationFindingSummary(
        total_findings=2,
        blocking_findings=1,
        top_blocking_finding_id="rf_1234567890abcdef",
        top_blocking_finding_type="missing_cashflow",
        top_blocking_finding_security_id="SEC-US-IBM",
        top_blocking_finding_transaction_id="txn_0001",
    )

    response = await service.get_support_overview("P1")

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2025, 8, 30)
    assert response.current_epoch == 2
    assert response.stale_threshold_minutes == 15
    assert response.failed_window_hours == 24
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.active_reprocessing_keys == 1
    assert response.stale_reprocessing_keys == 1
    assert response.oldest_reprocessing_watermark_date == date(2025, 8, 18)
    assert response.oldest_reprocessing_security_id == "S1"
    assert response.oldest_reprocessing_epoch == 3
    assert response.oldest_reprocessing_updated_at == datetime(
        2025, 8, 30, 9, 45, tzinfo=timezone.utc
    )
    assert response.reprocessing_backlog_age_days == 12
    assert response.pending_valuation_jobs == 4
    assert response.processing_valuation_jobs == 2
    assert response.stale_processing_valuation_jobs == 1
    assert response.failed_valuation_jobs == 0
    assert response.failed_valuation_jobs_within_window == 0
    assert response.oldest_pending_valuation_date == date(2025, 8, 20)
    assert response.oldest_pending_valuation_job_id == 8801
    assert response.oldest_pending_valuation_security_id == "SEC-US-IBM"
    assert response.oldest_pending_valuation_correlation_id == "corr-val-8801"
    assert response.valuation_backlog_age_days == 10
    assert response.pending_aggregation_jobs == 1
    assert response.processing_aggregation_jobs == 0
    assert response.stale_processing_aggregation_jobs == 0
    assert response.failed_aggregation_jobs == 0
    assert response.failed_aggregation_jobs_within_window == 0
    assert response.oldest_pending_aggregation_date is None
    assert response.oldest_pending_aggregation_job_id is None
    assert response.oldest_pending_aggregation_correlation_id is None
    assert response.aggregation_backlog_age_days is None
    assert response.pending_analytics_export_jobs == 2
    assert response.processing_analytics_export_jobs == 1
    assert response.stale_processing_analytics_export_jobs == 0
    assert response.failed_analytics_export_jobs == 1
    assert response.failed_analytics_export_jobs_within_window == 1
    assert response.oldest_pending_analytics_export_created_at == datetime(
        2025, 8, 30, 10, 0, tzinfo=timezone.utc
    )
    assert response.oldest_pending_analytics_export_job_id == "aexp_0001"
    assert response.oldest_pending_analytics_export_request_fingerprint == "pf-001:positions:csv"
    assert response.analytics_export_backlog_age_minutes is not None
    assert response.latest_transaction_date == date(2025, 9, 2)
    assert response.latest_booked_transaction_date == date(2025, 8, 30)
    assert response.latest_position_snapshot_date == date(2025, 8, 30)
    assert response.latest_booked_position_snapshot_date == date(2025, 8, 30)
    assert response.position_snapshot_history_mismatch_count == 0
    assert response.controls_business_date == date(2025, 8, 30)
    assert response.controls_stage_id == 701
    assert response.controls_last_source_event_type == "financial_reconciliation_completed"
    assert response.controls_created_at == datetime(
        2025, 8, 30, 10, 10, tzinfo=timezone.utc
    )
    assert response.controls_ready_emitted_at == datetime(
        2025, 8, 30, 10, 14, tzinfo=timezone.utc
    )
    assert response.controls_epoch == 2
    assert response.controls_status == "COMPLETED"
    assert response.controls_failure_reason is None
    assert response.controls_latest_reconciliation_run_id == "recon_1234567890abcdef"
    assert response.controls_latest_reconciliation_type == "transaction_cashflow"
    assert response.controls_latest_reconciliation_status == "COMPLETED"
    assert response.controls_latest_reconciliation_correlation_id == "corr-recon-20250830-001"
    assert (
        response.controls_latest_reconciliation_requested_by
        == "pipeline_orchestrator_service"
    )
    assert (
        response.controls_latest_reconciliation_dedupe_key
        == "recon:transaction_cashflow:P1:2025-08-30:2"
    )
    assert response.controls_latest_reconciliation_failure_reason is None
    assert response.controls_latest_reconciliation_total_findings == 2
    assert response.controls_latest_reconciliation_blocking_findings == 1
    assert response.controls_latest_blocking_finding_id == "rf_1234567890abcdef"
    assert response.controls_latest_blocking_finding_type == "missing_cashflow"
    assert response.controls_latest_blocking_finding_security_id == "SEC-US-IBM"
    assert response.controls_latest_blocking_finding_transaction_id == "txn_0001"
    assert response.controls_last_updated_at == datetime(
        2025, 8, 30, 10, 15, tzinfo=timezone.utc
    )
    assert response.controls_blocking is False
    assert response.publish_allowed is True
    mock_ops_repo.get_position_snapshot_history_mismatch_count.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_current_portfolio_epoch.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_business_date.assert_awaited_once_with(
        as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_transaction_date.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_reprocessing_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_latest_transaction_date_as_of.assert_awaited_once_with(
        "P1",
        date(2025, 8, 30),
        snapshot_as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.assert_awaited_once_with(
        "P1",
        date(2025, 8, 30),
        snapshot_as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.assert_awaited_once()
    control_call = mock_ops_repo.get_latest_financial_reconciliation_control_stage.await_args
    assert control_call.args == ("P1",)
    assert control_call.kwargs["as_of"] == response.generated_at_utc


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

    assert response.generated_at_utc.tzinfo == timezone.utc
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
    mock_ops_repo.get_position_state.assert_awaited_once_with(
        "P1", "S1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_position_history_date.assert_awaited_once_with(
        "P1", "S1", 3, as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_daily_snapshot_date.assert_awaited_once_with(
        "P1", "S1", 3, as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_valuation_job.assert_awaited_once_with(
        "P1", "S1", 3, as_of=response.generated_at_utc
    )


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

    assert response.generated_at_utc.tzinfo == timezone.utc
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

    assert response.generated_at_utc.tzinfo == timezone.utc
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
    mock_ops_repo.get_lineage_keys_count.assert_awaited_once_with(
        portfolio_id="P1",
        reprocessing_status="CURRENT",
        security_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_lineage_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=10,
        reprocessing_status="CURRENT",
        security_id=None,
        as_of=response.generated_at_utc,
    )


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

    assert response.stale_threshold_minutes == 15
    assert response.generated_at_utc.tzinfo == timezone.utc
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
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
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

    assert response.stale_threshold_minutes == 15
    assert response.generated_at_utc.tzinfo == timezone.utc
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
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        business_date=None,
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PROCESSING",
        business_date=None,
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )


async def test_get_aggregation_jobs_honors_custom_stale_threshold(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    created_at = datetime(2025, 8, 31, 9, 45, tzinfo=timezone.utc)
    updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    mock_ops_repo.get_aggregation_jobs_count.return_value = 1
    mock_ops_repo.get_aggregation_jobs.return_value = [
        type(
            "AggregationJobStub",
            (),
            {
                "id": 203,
                "aggregation_date": date(2025, 8, 31),
                "status": "PROCESSING",
                "attempt_count": 1,
                "correlation_id": "corr-agg-203",
                "created_at": created_at,
                "updated_at": updated_at,
                "failure_reason": None,
            },
        )()
    ]

    response = await service.get_aggregation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        stale_threshold_minutes=30,
    )

    assert response.stale_threshold_minutes == 30
    assert response.items[0].is_stale_processing is False
    assert response.items[0].operational_state == "PROCESSING"
    mock_ops_repo.get_aggregation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        business_date=None,
        job_id=None,
        correlation_id=None,
        stale_minutes=30,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
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

    assert response.stale_threshold_minutes == 15
    assert response.generated_at_utc.tzinfo == timezone.utc
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
    mock_ops_repo.get_reprocessing_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PROCESSING",
        security_id="S1",
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reprocessing_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        security_id="S1",
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
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
            "PROCESSING",
            updated_at,
            now=datetime(2025, 8, 31, 10, 20, tzinfo=timezone.utc),
            stale_threshold_minutes=30,
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
                "request_fingerprint": "fp_portfolio_timeseries_pf001_20260313_v1",
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

    assert response.stale_threshold_minutes == 15
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.total == 1
    assert response.items[0].job_id == "aexp_1234567890abcdef"
    assert response.items[0].request_fingerprint == "fp_portfolio_timeseries_pf001_20260313_v1"
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
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="FAILED",
        job_id=None,
        request_fingerprint=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_analytics_export_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="FAILED",
        job_id=None,
        request_fingerprint=None,
        as_of=response.generated_at_utc,
    )


async def test_get_valuation_jobs_forwards_job_id_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_valuation_jobs.return_value = []

    response = await service.get_valuation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PENDING",
        job_id=8801,
    )

    assert response.total == 0
    mock_ops_repo.get_valuation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=8801,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=8801,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_valuation_jobs_forwards_security_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_valuation_jobs.return_value = []

    response = await service.get_valuation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PENDING",
        security_id="SEC-US-IBM",
    )

    assert response.total == 0
    mock_ops_repo.get_valuation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PENDING",
        business_date=None,
        security_id="SEC-US-IBM",
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=None,
        security_id="SEC-US-IBM",
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_valuation_jobs_forwards_correlation_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_valuation_jobs.return_value = []

    response = await service.get_valuation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PENDING",
        correlation_id="corr-val-8801",
    )

    assert response.total == 0
    mock_ops_repo.get_valuation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=None,
        correlation_id="corr-val-8801",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=None,
        security_id=None,
        job_id=None,
        correlation_id="corr-val-8801",
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_valuation_jobs_forwards_business_date_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_valuation_jobs.return_value = []

    response = await service.get_valuation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=date(2025, 8, 31),
    )

    assert response.total == 0
    mock_ops_repo.get_valuation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PENDING",
        business_date=date(2025, 8, 31),
        security_id=None,
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PENDING",
        business_date=date(2025, 8, 31),
        security_id=None,
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_aggregation_jobs_forwards_business_date_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_aggregation_jobs_count.return_value = 0
    mock_ops_repo.get_aggregation_jobs.return_value = []

    response = await service.get_aggregation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        business_date=date(2025, 8, 31),
    )

    assert response.total == 0
    mock_ops_repo.get_aggregation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PROCESSING",
        business_date=date(2025, 8, 31),
        job_id=None,
        correlation_id=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        business_date=date(2025, 8, 31),
        job_id=None,
        correlation_id=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_analytics_export_jobs_forwards_job_id_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_analytics_export_jobs_count.return_value = 0
    mock_ops_repo.get_analytics_export_jobs.return_value = []

    response = await service.get_analytics_export_jobs(
        "P1",
        skip=0,
        limit=20,
        status="FAILED",
        job_id="aexp_1234567890abcdef",
    )

    assert response.total == 0
    mock_ops_repo.get_analytics_export_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="FAILED",
        job_id="aexp_1234567890abcdef",
        request_fingerprint=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_analytics_export_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="FAILED",
        job_id="aexp_1234567890abcdef",
        request_fingerprint=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_aggregation_jobs_forwards_correlation_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_aggregation_jobs_count.return_value = 0
    mock_ops_repo.get_aggregation_jobs.return_value = []

    response = await service.get_aggregation_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        correlation_id="corr-agg-4402",
    )

    assert response.total == 0
    mock_ops_repo.get_aggregation_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PROCESSING",
        business_date=None,
        job_id=None,
        correlation_id="corr-agg-4402",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        business_date=None,
        job_id=None,
        correlation_id="corr-agg-4402",
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_analytics_export_jobs_forwards_request_fingerprint_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_analytics_export_jobs_count.return_value = 0
    mock_ops_repo.get_analytics_export_jobs.return_value = []

    response = await service.get_analytics_export_jobs(
        "P1",
        skip=0,
        limit=20,
        request_fingerprint="fp_portfolio_timeseries_pf001_20260313_v1",
        stale_threshold_minutes=30,
    )

    assert response.total == 0
    mock_ops_repo.get_analytics_export_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status=None,
        job_id=None,
        request_fingerprint="fp_portfolio_timeseries_pf001_20260313_v1",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_analytics_export_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status=None,
        job_id=None,
        request_fingerprint="fp_portfolio_timeseries_pf001_20260313_v1",
        stale_minutes=30,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_analytics_export_job_flags_running_staleness_and_backlog_age():
    created_at = datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 3, 13, 10, 5, tzinfo=timezone.utc)
    now = datetime(2026, 3, 13, 10, 30, tzinfo=timezone.utc)

    assert OperationsService._is_analytics_export_job_stale("running", updated_at, now=now) is True
    assert (
        OperationsService._is_analytics_export_job_stale(
            "running",
            updated_at,
            now=now,
            stale_threshold_minutes=30,
        )
        is False
    )
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
    assert (
        OperationsService._get_analytics_export_operational_state(
            "running",
            updated_at,
            now=now,
            stale_threshold_minutes=30,
        )
        == "RUNNING"
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
                "requested_by": "pipeline_orchestrator_service",
                "dedupe_key": "recon:transaction_cashflow:P1:2026-03-13:3",
                "correlation_id": "corr-recon-20260313-001",
                "failure_reason": "Tolerance exceeded for portfolio totals.",
            },
        )()
    ]

    response = await service.get_reconciliation_runs(
        "P1",
        skip=0,
        limit=20,
        run_id="recon_1234567890abcdef",
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
    )

    assert response.total == 1
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.items[0].run_id == "recon_1234567890abcdef"
    assert response.items[0].reconciliation_type == "transaction_cashflow"
    assert response.items[0].status == "FAILED"
    assert response.items[0].requested_by == "pipeline_orchestrator_service"
    assert response.items[0].dedupe_key == "recon:transaction_cashflow:P1:2026-03-13:3"
    assert response.items[0].correlation_id == "corr-recon-20260313-001"
    assert response.items[0].failure_reason == "Tolerance exceeded for portfolio totals."
    assert response.items[0].is_terminal_failure is True
    assert response.items[0].is_blocking is True
    assert response.items[0].operational_state == "BLOCKING"
    mock_ops_repo.get_reconciliation_runs_count.assert_awaited_once_with(
        portfolio_id="P1",
        run_id="recon_1234567890abcdef",
        correlation_id=None,
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reconciliation_runs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        run_id="recon_1234567890abcdef",
        correlation_id=None,
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
        as_of=response.generated_at_utc,
    )


async def test_get_reconciliation_runs_forwards_correlation_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_reconciliation_runs_count.return_value = 0
    mock_ops_repo.get_reconciliation_runs.return_value = []

    response = await service.get_reconciliation_runs(
        "P1",
        skip=0,
        limit=20,
        correlation_id="corr-recon-20260313-001",
        status="FAILED",
    )

    assert response.total == 0
    mock_ops_repo.get_reconciliation_runs_count.assert_awaited_once_with(
        portfolio_id="P1",
        run_id=None,
        correlation_id="corr-recon-20260313-001",
        requested_by=None,
        dedupe_key=None,
        reconciliation_type=None,
        status="FAILED",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reconciliation_runs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        run_id=None,
        correlation_id="corr-recon-20260313-001",
        requested_by=None,
        dedupe_key=None,
        reconciliation_type=None,
        status="FAILED",
        as_of=response.generated_at_utc,
    )


async def test_get_reconciliation_runs_forwards_requester_and_dedupe_filters(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_reconciliation_runs_count.return_value = 0
    mock_ops_repo.get_reconciliation_runs.return_value = []

    response = await service.get_reconciliation_runs(
        "P1",
        skip=0,
        limit=20,
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        status="FAILED",
    )

    assert response.total == 0
    mock_ops_repo.get_reconciliation_runs_count.assert_awaited_once_with(
        portfolio_id="P1",
        run_id=None,
        correlation_id=None,
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        reconciliation_type=None,
        status="FAILED",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reconciliation_runs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        run_id=None,
        correlation_id=None,
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-03-13:3",
        reconciliation_type=None,
        status="FAILED",
        as_of=response.generated_at_utc,
    )


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
        finding_id="rf_1234567890abcdef",
        security_id="SEC-US-IBM",
        transaction_id="TXN-20260313-0042",
    )

    assert response.run_id == "recon_1234567890abcdef"
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.total == 7
    assert response.items[0].finding_id == "rf_1234567890abcdef"
    assert response.items[0].severity == "ERROR"
    assert response.items[0].detail == {"expected_cashflow_count": 1, "observed_cashflow_count": 0}
    mock_ops_repo.get_reconciliation_findings_count.assert_awaited_once_with(
        run_id="recon_1234567890abcdef",
        finding_id="rf_1234567890abcdef",
        security_id="SEC-US-IBM",
        transaction_id="TXN-20260313-0042",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reconciliation_findings.assert_awaited_once_with(
        run_id="recon_1234567890abcdef",
        limit=50,
        finding_id="rf_1234567890abcdef",
        security_id="SEC-US-IBM",
        transaction_id="TXN-20260313-0042",
        as_of=response.generated_at_utc,
    )
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
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )

    assert response.portfolio_id == "P1"
    assert response.generated_at_utc.tzinfo == timezone.utc
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
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_portfolio_control_stages_count.assert_awaited_once_with(
        portfolio_id="P1",
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
        as_of=response.generated_at_utc,
    )


async def test_get_reprocessing_keys(service: OperationsService, mock_ops_repo: AsyncMock):
    created_at = datetime(2026, 3, 13, 10, 5, tzinfo=timezone.utc)
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
                "created_at": created_at,
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
    assert response.stale_threshold_minutes == 15
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.total == 1
    assert response.items[0].security_id == "SEC-US-IBM"
    assert response.items[0].epoch == 3
    assert response.items[0].watermark_date == date(2026, 3, 10)
    assert response.items[0].status == "REPROCESSING"
    assert response.items[0].created_at == created_at
    assert response.items[0].updated_at == updated_at
    assert response.items[0].is_stale_reprocessing is False
    assert response.items[0].operational_state == "REPROCESSING"
    mock_ops_repo.get_reprocessing_keys_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        watermark_date=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reprocessing_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        watermark_date=None,
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_reprocessing_keys_honors_custom_stale_threshold(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    created_at = datetime(2026, 3, 13, 9, 30, tzinfo=timezone.utc)
    updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    mock_ops_repo.get_reprocessing_keys_count.return_value = 1
    mock_ops_repo.get_reprocessing_keys.return_value = [
        type(
            "ReprocessingKeyStub",
            (),
            {
                "security_id": "SEC-US-IBM",
                "epoch": 3,
                "watermark_date": date(2026, 3, 10),
                "status": "REPROCESSING",
                "created_at": created_at,
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
        stale_threshold_minutes=30,
    )

    assert response.stale_threshold_minutes == 30
    assert response.items[0].is_stale_reprocessing is False
    assert response.items[0].operational_state == "REPROCESSING"
    mock_ops_repo.get_reprocessing_keys_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        watermark_date=None,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reprocessing_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        watermark_date=None,
        stale_minutes=30,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_reprocessing_keys_forwards_watermark_date_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_reprocessing_keys_count.return_value = 0
    mock_ops_repo.get_reprocessing_keys.return_value = []

    response = await service.get_reprocessing_keys(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        watermark_date=date(2026, 3, 10),
    )

    assert response.total == 0
    mock_ops_repo.get_reprocessing_keys_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="REPROCESSING",
        security_id=None,
        watermark_date=date(2026, 3, 10),
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reprocessing_keys.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=50,
        status="REPROCESSING",
        security_id=None,
        watermark_date=date(2026, 3, 10),
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_reprocessing_jobs_forwards_correlation_filter(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_reprocessing_jobs_count.return_value = 0
    mock_ops_repo.get_reprocessing_jobs.return_value = []

    response = await service.get_reprocessing_jobs(
        "P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        correlation_id="corr-replay-303",
    )

    assert response.total == 0
    mock_ops_repo.get_reprocessing_jobs_count.assert_awaited_once_with(
        portfolio_id="P1",
        status="PROCESSING",
        security_id=None,
        job_id=None,
        correlation_id="corr-replay-303",
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_reprocessing_jobs.assert_awaited_once_with(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status="PROCESSING",
        security_id=None,
        job_id=None,
        correlation_id="corr-replay-303",
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )


async def test_get_support_overview_raises_when_portfolio_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.portfolio_exists.return_value = False

    with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
        await service.get_support_overview("P404")


async def test_get_support_overview_honors_custom_stale_threshold(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_current_portfolio_epoch.return_value = 1
    mock_ops_repo.get_reprocessing_health_summary.return_value = ReprocessingHealthSummary(
        active_keys=0,
        stale_reprocessing_keys=0,
        oldest_reprocessing_watermark_date=None,
        oldest_reprocessing_security_id=None,
        oldest_reprocessing_epoch=None,
        oldest_reprocessing_updated_at=None,
    )
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=0,
        running_jobs=0,
        stale_running_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_created_at=None,
        oldest_open_job_id=None,
        oldest_open_request_fingerprint=None,
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(
        2025, 8, 30
    )
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = None
    mock_ops_repo.get_latest_reconciliation_run_for_portfolio_day.return_value = None

    response = await service.get_support_overview(
        "P1", stale_threshold_minutes=30, failed_window_hours=48
    )

    assert response.stale_threshold_minutes == 30
    assert response.failed_window_hours == 48
    assert response.generated_at_utc.tzinfo == timezone.utc
    mock_ops_repo.get_reprocessing_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=30,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=30,
        failed_window_hours=48,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=30,
        failed_window_hours=48,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=30,
        failed_window_hours=48,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_latest_transaction_date_as_of.assert_awaited_once_with(
        "P1",
        date(2025, 8, 30),
        snapshot_as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.assert_awaited_once_with(
        "P1",
        date(2025, 8, 30),
        snapshot_as_of=response.generated_at_utc,
    )


async def test_get_support_overview_without_business_date(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = None
    mock_ops_repo.get_current_portfolio_epoch.return_value = 1
    mock_ops_repo.get_reprocessing_health_summary.return_value = ReprocessingHealthSummary(
        active_keys=0,
        stale_reprocessing_keys=0,
        oldest_reprocessing_watermark_date=None,
        oldest_reprocessing_security_id=None,
        oldest_reprocessing_epoch=None,
        oldest_reprocessing_updated_at=None,
    )
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=0,
        running_jobs=0,
        stale_running_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_created_at=None,
        oldest_open_job_id=None,
        oldest_open_request_fingerprint=None,
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 31)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = None
    mock_ops_repo.get_latest_reconciliation_run_for_portfolio_day.return_value = None

    response = await service.get_support_overview("P1")

    assert response.business_date is None
    assert response.stale_threshold_minutes == 15
    assert response.failed_window_hours == 24
    assert response.generated_at_utc.tzinfo == timezone.utc
    assert response.stale_reprocessing_keys == 0
    assert response.oldest_reprocessing_watermark_date is None
    assert response.oldest_reprocessing_security_id is None
    assert response.oldest_reprocessing_epoch is None
    assert response.oldest_reprocessing_updated_at is None
    assert response.reprocessing_backlog_age_days is None
    assert response.valuation_backlog_age_days is None
    assert response.aggregation_backlog_age_days is None
    assert response.pending_analytics_export_jobs == 0
    assert response.processing_analytics_export_jobs == 0
    assert response.stale_processing_analytics_export_jobs == 0
    assert response.failed_analytics_export_jobs == 0
    assert response.failed_analytics_export_jobs_within_window == 0
    assert response.oldest_pending_analytics_export_created_at is None
    assert response.oldest_pending_analytics_export_job_id is None
    assert response.oldest_pending_analytics_export_request_fingerprint is None
    assert response.analytics_export_backlog_age_minutes is None
    assert response.oldest_pending_valuation_security_id is None
    assert response.oldest_pending_valuation_correlation_id is None
    assert response.oldest_pending_aggregation_correlation_id is None
    assert response.latest_booked_transaction_date is None
    assert response.latest_booked_position_snapshot_date is None
    assert response.controls_status is None
    assert response.controls_stage_id is None
    assert response.controls_last_source_event_type is None
    assert response.controls_created_at is None
    assert response.controls_ready_emitted_at is None
    assert response.controls_failure_reason is None
    assert response.controls_latest_reconciliation_run_id is None
    assert response.controls_latest_reconciliation_type is None
    assert response.controls_latest_reconciliation_status is None
    assert response.controls_latest_reconciliation_correlation_id is None
    assert response.controls_latest_reconciliation_requested_by is None
    assert response.controls_latest_reconciliation_dedupe_key is None
    assert response.controls_latest_reconciliation_failure_reason is None
    assert response.controls_latest_reconciliation_total_findings is None
    assert response.controls_latest_reconciliation_blocking_findings is None
    assert response.controls_latest_blocking_finding_id is None
    assert response.controls_latest_blocking_finding_type is None
    assert response.controls_latest_blocking_finding_security_id is None
    assert response.controls_latest_blocking_finding_transaction_id is None
    assert response.controls_last_updated_at is None
    assert response.controls_blocking is False
    assert response.publish_allowed is True
    mock_ops_repo.get_latest_transaction_date_as_of.assert_not_awaited()
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.assert_not_awaited()


async def test_get_support_overview_marks_publish_blocked_when_controls_require_replay(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_current_portfolio_epoch.return_value = 2
    mock_ops_repo.get_reprocessing_health_summary.return_value = ReprocessingHealthSummary(
        active_keys=0,
        stale_reprocessing_keys=0,
        oldest_reprocessing_watermark_date=None,
        oldest_reprocessing_security_id=None,
        oldest_reprocessing_epoch=None,
        oldest_reprocessing_updated_at=None,
    )
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=0,
        processing_jobs=0,
        stale_processing_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_date=None,
        oldest_open_job_id=None,
        oldest_open_job_correlation_id=None,
        oldest_open_security_id=None,
    )
    mock_ops_repo.get_analytics_export_job_health_summary.return_value = ExportJobHealthSummary(
        accepted_jobs=0,
        running_jobs=0,
        stale_running_jobs=0,
        failed_jobs=0,
        failed_jobs_last_hours=0,
        oldest_open_job_created_at=None,
        oldest_open_job_id=None,
        oldest_open_request_fingerprint=None,
    )
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.return_value = type(
        "ControlStageStub",
        (),
        {
            "id": 702,
            "business_date": date(2025, 8, 30),
            "epoch": 2,
            "status": "FAILED",
            "failure_reason": "Tolerance exceeded for portfolio totals.",
            "last_source_event_type": "financial_reconciliation_completed",
            "created_at": datetime(2025, 8, 30, 10, 40, tzinfo=timezone.utc),
            "ready_emitted_at": None,
            "updated_at": datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc),
        },
    )()
    mock_ops_repo.get_latest_reconciliation_run_for_portfolio_day.return_value = type(
        "ReconciliationRunStub",
        (),
        {
            "run_id": "recon_failed_20250830",
            "reconciliation_type": "transaction_cashflow",
            "status": "FAILED",
            "correlation_id": "corr-recon-20250830-failed",
            "requested_by": "pipeline_orchestrator_service",
            "dedupe_key": "recon:transaction_cashflow:P1:2025-08-30:2",
            "failure_reason": "Tolerance exceeded for portfolio totals.",
        },
    )()
    mock_ops_repo.get_reconciliation_finding_summary.return_value = ReconciliationFindingSummary(
        total_findings=3,
        blocking_findings=2,
        top_blocking_finding_id="rf_failed_20250830_01",
        top_blocking_finding_type="valuation_mismatch",
        top_blocking_finding_security_id="SEC-US-MSFT",
        top_blocking_finding_transaction_id="txn_0099",
    )

    response = await service.get_support_overview("P1")

    assert response.controls_stage_id == 702
    assert response.controls_last_source_event_type == "financial_reconciliation_completed"
    assert response.controls_created_at == datetime(
        2025, 8, 30, 10, 40, tzinfo=timezone.utc
    )
    assert response.controls_ready_emitted_at is None
    assert response.controls_status == "FAILED"
    assert response.controls_failure_reason == "Tolerance exceeded for portfolio totals."
    assert response.controls_latest_reconciliation_run_id == "recon_failed_20250830"
    assert response.controls_latest_reconciliation_type == "transaction_cashflow"
    assert response.controls_latest_reconciliation_status == "FAILED"
    assert (
        response.controls_latest_reconciliation_correlation_id
        == "corr-recon-20250830-failed"
    )
    assert (
        response.controls_latest_reconciliation_requested_by
        == "pipeline_orchestrator_service"
    )
    assert (
        response.controls_latest_reconciliation_dedupe_key
        == "recon:transaction_cashflow:P1:2025-08-30:2"
    )
    assert (
        response.controls_latest_reconciliation_failure_reason
        == "Tolerance exceeded for portfolio totals."
    )
    assert response.controls_latest_reconciliation_total_findings == 3
    assert response.controls_latest_reconciliation_blocking_findings == 2
    assert response.controls_latest_blocking_finding_id == "rf_failed_20250830_01"
    assert response.controls_latest_blocking_finding_type == "valuation_mismatch"
    assert response.controls_latest_blocking_finding_security_id == "SEC-US-MSFT"
    assert response.controls_latest_blocking_finding_transaction_id == "txn_0099"
    assert response.controls_last_updated_at == datetime(
        2025, 8, 30, 11, 0, tzinfo=timezone.utc
    )
    assert response.controls_blocking is True
    assert response.publish_allowed is False
    mock_ops_repo.get_position_snapshot_history_mismatch_count.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_current_portfolio_epoch.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_business_date.assert_awaited_once_with(
        as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_transaction_date.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.assert_awaited_once_with(
        "P1", as_of=response.generated_at_utc
    )
    mock_ops_repo.get_latest_financial_reconciliation_control_stage.assert_awaited_once()
    control_call = mock_ops_repo.get_latest_financial_reconciliation_control_stage.await_args
    assert control_call.args == ("P1",)
    assert control_call.kwargs["as_of"] == response.generated_at_utc
    mock_ops_repo.get_latest_reconciliation_run_for_portfolio_day.assert_awaited_once_with(
        portfolio_id="P1",
        business_date=date(2025, 8, 30),
        epoch=2,
        as_of=datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc),
    )
    mock_ops_repo.get_reconciliation_finding_summary.assert_awaited_once_with(
        "recon_failed_20250830",
        as_of=datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc),
    )


async def test_get_calculator_slos(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_reprocessing_health_summary.return_value = ReprocessingHealthSummary(
        active_keys=2,
        stale_reprocessing_keys=1,
        oldest_reprocessing_watermark_date=date(2025, 8, 18),
        oldest_reprocessing_security_id="S2",
        oldest_reprocessing_epoch=5,
        oldest_reprocessing_updated_at=datetime(2025, 8, 29, 8, 30, tzinfo=timezone.utc),
    )
    mock_ops_repo.get_valuation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=7,
        processing_jobs=3,
        stale_processing_jobs=1,
        failed_jobs=4,
        failed_jobs_last_hours=2,
        oldest_open_job_date=date(2025, 8, 20),
        oldest_open_job_id=8802,
        oldest_open_job_correlation_id="corr-val-8802",
        oldest_open_security_id="SEC-US-MSFT",
    )
    mock_ops_repo.get_aggregation_job_health_summary.return_value = JobHealthSummary(
        pending_jobs=5,
        processing_jobs=2,
        stale_processing_jobs=1,
        failed_jobs=1,
        failed_jobs_last_hours=1,
        oldest_open_job_date=date(2025, 8, 25),
        oldest_open_job_id=4402,
        oldest_open_job_correlation_id="corr-agg-4402",
        oldest_open_security_id=None,
    )

    response = await service.get_calculator_slos(
        "P1", stale_threshold_minutes=15, failed_window_hours=48
    )

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2025, 8, 30)
    assert response.stale_threshold_minutes == 15
    assert response.failed_window_hours == 48
    assert response.valuation.pending_jobs == 7
    assert response.valuation.failed_jobs == 4
    assert response.valuation.failed_jobs_within_window == 2
    assert response.valuation.oldest_open_job_id == 8802
    assert response.valuation.oldest_open_job_correlation_id == "corr-val-8802"
    assert response.valuation.backlog_age_days == 10
    assert response.aggregation.pending_jobs == 5
    assert response.aggregation.failed_jobs == 1
    assert response.aggregation.failed_jobs_within_window == 1
    assert response.aggregation.oldest_open_job_id == 4402
    assert response.aggregation.oldest_open_job_correlation_id == "corr-agg-4402"
    assert response.aggregation.backlog_age_days == 5
    assert response.reprocessing.active_reprocessing_keys == 2
    assert response.reprocessing.stale_reprocessing_keys == 1
    assert response.reprocessing.oldest_reprocessing_watermark_date == date(2025, 8, 18)
    assert response.reprocessing.oldest_reprocessing_security_id == "S2"
    assert response.reprocessing.oldest_reprocessing_epoch == 5
    assert response.reprocessing.oldest_reprocessing_updated_at == datetime(
        2025, 8, 29, 8, 30, tzinfo=timezone.utc
    )
    assert response.reprocessing.backlog_age_days == 12
    mock_ops_repo.get_latest_business_date.assert_awaited_once_with(
        as_of=response.generated_at_utc
    )
    mock_ops_repo.get_reprocessing_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_valuation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        failed_window_hours=48,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
    mock_ops_repo.get_aggregation_job_health_summary.assert_awaited_once_with(
        "P1",
        stale_minutes=15,
        failed_window_hours=48,
        reference_now=response.generated_at_utc,
        as_of=response.generated_at_utc,
    )
