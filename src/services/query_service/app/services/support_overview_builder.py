from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from portfolio_common.database_models import FinancialReconciliationRun, PipelineStageState

from ..dtos.operations_dto import SupportOverviewResponse
from ..repositories.operations_models import (
    ExportJobHealthSummary,
    JobHealthSummary,
    ReconciliationFindingSummary,
    ReprocessingHealthSummary,
)


@dataclass(frozen=True)
class SupportOverviewSnapshot:
    portfolio_id: str
    stale_threshold_minutes: int
    failed_window_hours: int
    generated_at_utc: datetime
    latest_business_date: date | None
    current_epoch: int | None
    reprocessing_health: ReprocessingHealthSummary
    valuation_job_health: JobHealthSummary
    aggregation_job_health: JobHealthSummary
    analytics_export_job_health: ExportJobHealthSummary
    latest_transaction_date: date | None
    latest_booked_transaction_date: date | None
    latest_position_snapshot_date: date | None
    latest_booked_position_snapshot_date: date | None
    position_snapshot_history_mismatch_count: int
    latest_control_stage: PipelineStageState | None
    latest_reconciliation_run: FinancialReconciliationRun | None
    latest_reconciliation_finding_summary: ReconciliationFindingSummary | None
    controls_blocking: bool


def _backlog_age_days(
    oldest_date: date | None,
    *,
    latest_business_date: date | None,
    generated_at_utc: datetime,
) -> int | None:
    if oldest_date is None:
        return None
    reference_date = latest_business_date or generated_at_utc.date()
    return max(0, (reference_date - oldest_date).days)


def _backlog_age_minutes(
    oldest_timestamp: datetime | None,
    *,
    generated_at_utc: datetime,
) -> int | None:
    if oldest_timestamp is None:
        return None
    delta = generated_at_utc - oldest_timestamp
    return max(0, int(delta.total_seconds() // 60))


def _field_value(source: object | None, field_name: str) -> Any | None:
    if source is None:
        return None
    return getattr(source, field_name, None)


def _reprocessing_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    reprocessing_health = snapshot.reprocessing_health
    return {
        "active_reprocessing_keys": reprocessing_health.active_keys,
        "stale_reprocessing_keys": reprocessing_health.stale_reprocessing_keys,
        "oldest_reprocessing_watermark_date": (
            reprocessing_health.oldest_reprocessing_watermark_date
        ),
        "oldest_reprocessing_security_id": reprocessing_health.oldest_reprocessing_security_id,
        "oldest_reprocessing_epoch": reprocessing_health.oldest_reprocessing_epoch,
        "oldest_reprocessing_updated_at": reprocessing_health.oldest_reprocessing_updated_at,
        "reprocessing_backlog_age_days": _backlog_age_days(
            reprocessing_health.oldest_reprocessing_watermark_date,
            latest_business_date=snapshot.latest_business_date,
            generated_at_utc=snapshot.generated_at_utc,
        ),
    }


def _valuation_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    valuation_job_health = snapshot.valuation_job_health
    return {
        "pending_valuation_jobs": valuation_job_health.pending_jobs,
        "processing_valuation_jobs": valuation_job_health.processing_jobs,
        "stale_processing_valuation_jobs": valuation_job_health.stale_processing_jobs,
        "failed_valuation_jobs": valuation_job_health.failed_jobs,
        "failed_valuation_jobs_within_window": valuation_job_health.failed_jobs_last_hours,
        "oldest_pending_valuation_date": valuation_job_health.oldest_open_job_date,
        "oldest_pending_valuation_job_id": valuation_job_health.oldest_open_job_id,
        "oldest_pending_valuation_security_id": valuation_job_health.oldest_open_security_id,
        "oldest_pending_valuation_correlation_id": (
            valuation_job_health.oldest_open_job_correlation_id
        ),
        "valuation_backlog_age_days": _backlog_age_days(
            valuation_job_health.oldest_open_job_date,
            latest_business_date=snapshot.latest_business_date,
            generated_at_utc=snapshot.generated_at_utc,
        ),
    }


def _aggregation_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    aggregation_job_health = snapshot.aggregation_job_health
    return {
        "pending_aggregation_jobs": aggregation_job_health.pending_jobs,
        "processing_aggregation_jobs": aggregation_job_health.processing_jobs,
        "stale_processing_aggregation_jobs": aggregation_job_health.stale_processing_jobs,
        "failed_aggregation_jobs": aggregation_job_health.failed_jobs,
        "failed_aggregation_jobs_within_window": aggregation_job_health.failed_jobs_last_hours,
        "oldest_pending_aggregation_date": aggregation_job_health.oldest_open_job_date,
        "oldest_pending_aggregation_job_id": aggregation_job_health.oldest_open_job_id,
        "oldest_pending_aggregation_correlation_id": (
            aggregation_job_health.oldest_open_job_correlation_id
        ),
        "aggregation_backlog_age_days": _backlog_age_days(
            aggregation_job_health.oldest_open_job_date,
            latest_business_date=snapshot.latest_business_date,
            generated_at_utc=snapshot.generated_at_utc,
        ),
    }


def _analytics_export_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    analytics_export_job_health = snapshot.analytics_export_job_health
    return {
        "pending_analytics_export_jobs": analytics_export_job_health.accepted_jobs,
        "processing_analytics_export_jobs": analytics_export_job_health.running_jobs,
        "stale_processing_analytics_export_jobs": (analytics_export_job_health.stale_running_jobs),
        "failed_analytics_export_jobs": analytics_export_job_health.failed_jobs,
        "failed_analytics_export_jobs_within_window": (
            analytics_export_job_health.failed_jobs_last_hours
        ),
        "oldest_pending_analytics_export_created_at": (
            analytics_export_job_health.oldest_open_job_created_at
        ),
        "oldest_pending_analytics_export_job_id": analytics_export_job_health.oldest_open_job_id,
        "oldest_pending_analytics_export_request_fingerprint": (
            analytics_export_job_health.oldest_open_request_fingerprint
        ),
        "analytics_export_backlog_age_minutes": _backlog_age_minutes(
            analytics_export_job_health.oldest_open_job_created_at,
            generated_at_utc=snapshot.generated_at_utc,
        ),
    }


def _portfolio_evidence_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    return {
        "latest_transaction_date": snapshot.latest_transaction_date,
        "latest_booked_transaction_date": snapshot.latest_booked_transaction_date,
        "latest_position_snapshot_date": snapshot.latest_position_snapshot_date,
        "latest_booked_position_snapshot_date": (snapshot.latest_booked_position_snapshot_date),
        "position_snapshot_history_mismatch_count": (
            snapshot.position_snapshot_history_mismatch_count
        ),
    }


def _control_stage_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    latest_control_stage = snapshot.latest_control_stage
    return {
        "controls_business_date": _field_value(latest_control_stage, "business_date"),
        "controls_stage_id": _field_value(latest_control_stage, "id"),
        "controls_last_source_event_type": _field_value(
            latest_control_stage, "last_source_event_type"
        ),
        "controls_created_at": _field_value(latest_control_stage, "created_at"),
        "controls_ready_emitted_at": _field_value(latest_control_stage, "ready_emitted_at"),
        "controls_epoch": _field_value(latest_control_stage, "epoch"),
        "controls_status": _field_value(latest_control_stage, "status"),
        "controls_failure_reason": _field_value(latest_control_stage, "failure_reason"),
        "controls_last_updated_at": _field_value(latest_control_stage, "updated_at"),
    }


def _reconciliation_run_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    latest_reconciliation_run = snapshot.latest_reconciliation_run
    return {
        "controls_latest_reconciliation_run_id": _field_value(latest_reconciliation_run, "run_id"),
        "controls_latest_reconciliation_type": _field_value(
            latest_reconciliation_run, "reconciliation_type"
        ),
        "controls_latest_reconciliation_status": _field_value(latest_reconciliation_run, "status"),
        "controls_latest_reconciliation_correlation_id": _field_value(
            latest_reconciliation_run, "correlation_id"
        ),
        "controls_latest_reconciliation_requested_by": _field_value(
            latest_reconciliation_run, "requested_by"
        ),
        "controls_latest_reconciliation_dedupe_key": _field_value(
            latest_reconciliation_run, "dedupe_key"
        ),
        "controls_latest_reconciliation_failure_reason": _field_value(
            latest_reconciliation_run, "failure_reason"
        ),
    }


def _reconciliation_finding_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    latest_reconciliation_finding_summary = snapshot.latest_reconciliation_finding_summary
    return {
        "controls_latest_reconciliation_total_findings": _field_value(
            latest_reconciliation_finding_summary, "total_findings"
        ),
        "controls_latest_reconciliation_blocking_findings": _field_value(
            latest_reconciliation_finding_summary, "blocking_findings"
        ),
        "controls_latest_blocking_finding_id": _field_value(
            latest_reconciliation_finding_summary, "top_blocking_finding_id"
        ),
        "controls_latest_blocking_finding_type": _field_value(
            latest_reconciliation_finding_summary, "top_blocking_finding_type"
        ),
        "controls_latest_blocking_finding_security_id": _field_value(
            latest_reconciliation_finding_summary, "top_blocking_finding_security_id"
        ),
        "controls_latest_blocking_finding_transaction_id": _field_value(
            latest_reconciliation_finding_summary, "top_blocking_finding_transaction_id"
        ),
    }


def _control_fields(snapshot: SupportOverviewSnapshot) -> dict[str, Any]:
    return {
        **_control_stage_fields(snapshot),
        **_reconciliation_run_fields(snapshot),
        **_reconciliation_finding_fields(snapshot),
        "controls_blocking": snapshot.controls_blocking,
        "publish_allowed": not snapshot.controls_blocking,
    }


def build_support_overview_response(snapshot: SupportOverviewSnapshot) -> SupportOverviewResponse:
    return SupportOverviewResponse(
        portfolio_id=snapshot.portfolio_id,
        business_date=snapshot.latest_business_date,
        current_epoch=snapshot.current_epoch,
        stale_threshold_minutes=snapshot.stale_threshold_minutes,
        failed_window_hours=snapshot.failed_window_hours,
        generated_at_utc=snapshot.generated_at_utc,
        **_reprocessing_fields(snapshot),
        **_valuation_fields(snapshot),
        **_aggregation_fields(snapshot),
        **_analytics_export_fields(snapshot),
        **_portfolio_evidence_fields(snapshot),
        **_control_fields(snapshot),
    )
