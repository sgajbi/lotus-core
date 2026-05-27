from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.services.query_service.app.repositories.operations_repository import (
    ExportJobHealthSummary,
    JobHealthSummary,
    ReconciliationFindingSummary,
    ReprocessingHealthSummary,
)
from src.services.query_service.app.services.support_overview_builder import (
    SupportOverviewSnapshot,
    build_support_overview_response,
)


def _empty_job_health() -> JobHealthSummary:
    return JobHealthSummary(
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


def test_build_support_overview_response_derives_backlog_and_control_state():
    generated_at = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    control_stage = SimpleNamespace(
        id=701,
        business_date=date(2026, 5, 24),
        epoch=4,
        status="REQUIRES_REPLAY",
        failure_reason="cashflow break",
        last_source_event_type="portfolio_day.reconciliation.failed",
        created_at=datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc),
        ready_emitted_at=None,
        updated_at=datetime(2026, 5, 24, 10, 5, tzinfo=timezone.utc),
    )
    reconciliation_run = SimpleNamespace(
        run_id="recon_20260524_001",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
        correlation_id="corr-recon-001",
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2026-05-24:4",
        failure_reason="blocking cashflow mismatch",
    )

    response = build_support_overview_response(
        SupportOverviewSnapshot(
            portfolio_id="P1",
            stale_threshold_minutes=15,
            failed_window_hours=24,
            generated_at_utc=generated_at,
            latest_business_date=date(2026, 5, 26),
            current_epoch=4,
            reprocessing_health=ReprocessingHealthSummary(
                active_keys=1,
                stale_reprocessing_keys=1,
                oldest_reprocessing_watermark_date=date(2026, 5, 20),
                oldest_reprocessing_security_id="SEC-US-IBM",
                oldest_reprocessing_epoch=4,
                oldest_reprocessing_updated_at=datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc),
            ),
            valuation_job_health=JobHealthSummary(
                pending_jobs=2,
                processing_jobs=1,
                stale_processing_jobs=1,
                failed_jobs=1,
                failed_jobs_last_hours=1,
                oldest_open_job_date=date(2026, 5, 22),
                oldest_open_job_id=8801,
                oldest_open_job_correlation_id="corr-val-001",
                oldest_open_security_id="SEC-US-IBM",
            ),
            aggregation_job_health=_empty_job_health(),
            analytics_export_job_health=ExportJobHealthSummary(
                accepted_jobs=1,
                running_jobs=1,
                stale_running_jobs=0,
                failed_jobs=0,
                failed_jobs_last_hours=0,
                oldest_open_job_created_at=datetime(2026, 5, 27, 10, 30, tzinfo=timezone.utc),
                oldest_open_job_id="aexp_001",
                oldest_open_request_fingerprint="P1:positions:csv",
            ),
            latest_transaction_date=date(2026, 5, 25),
            latest_booked_transaction_date=date(2026, 5, 24),
            latest_position_snapshot_date=date(2026, 5, 26),
            latest_booked_position_snapshot_date=date(2026, 5, 24),
            position_snapshot_history_mismatch_count=0,
            latest_control_stage=control_stage,
            latest_reconciliation_run=reconciliation_run,
            latest_reconciliation_finding_summary=ReconciliationFindingSummary(
                total_findings=3,
                blocking_findings=2,
                top_blocking_finding_id="rf_001",
                top_blocking_finding_type="valuation_mismatch",
                top_blocking_finding_security_id="SEC-US-IBM",
                top_blocking_finding_transaction_id="txn_001",
            ),
            controls_blocking=True,
        )
    )

    assert response.reprocessing_backlog_age_days == 6
    assert response.valuation_backlog_age_days == 4
    assert response.analytics_export_backlog_age_minutes == 90
    assert response.controls_status == "REQUIRES_REPLAY"
    assert response.controls_latest_reconciliation_run_id == "recon_20260524_001"
    assert response.controls_latest_blocking_finding_id == "rf_001"
    assert response.controls_blocking is True
    assert response.publish_allowed is False


def test_build_support_overview_response_uses_generated_date_when_business_date_missing():
    generated_at = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)

    response = build_support_overview_response(
        SupportOverviewSnapshot(
            portfolio_id="P1",
            stale_threshold_minutes=15,
            failed_window_hours=24,
            generated_at_utc=generated_at,
            latest_business_date=None,
            current_epoch=None,
            reprocessing_health=ReprocessingHealthSummary(
                active_keys=0,
                stale_reprocessing_keys=0,
                oldest_reprocessing_watermark_date=date(2026, 5, 25),
                oldest_reprocessing_security_id=None,
                oldest_reprocessing_epoch=None,
                oldest_reprocessing_updated_at=None,
            ),
            valuation_job_health=_empty_job_health(),
            aggregation_job_health=_empty_job_health(),
            analytics_export_job_health=ExportJobHealthSummary(
                accepted_jobs=0,
                running_jobs=0,
                stale_running_jobs=0,
                failed_jobs=0,
                failed_jobs_last_hours=0,
                oldest_open_job_created_at=None,
                oldest_open_job_id=None,
                oldest_open_request_fingerprint=None,
            ),
            latest_transaction_date=None,
            latest_booked_transaction_date=None,
            latest_position_snapshot_date=None,
            latest_booked_position_snapshot_date=None,
            position_snapshot_history_mismatch_count=0,
            latest_control_stage=None,
            latest_reconciliation_run=None,
            latest_reconciliation_finding_summary=None,
            controls_blocking=False,
        )
    )

    assert response.reprocessing_backlog_age_days == 2
    assert response.business_date is None
    assert response.controls_status is None
    assert response.publish_allowed is True
