from datetime import date, datetime

from ..dtos.operations_dto import (
    CalculatorSloBucket,
    CalculatorSloResponse,
    ReprocessingSloBucket,
)
from ..repositories.operations_models import JobHealthSummary, ReprocessingHealthSummary


def _backlog_age_days(
    oldest_date: date | None,
    *,
    reference_date: date,
) -> int | None:
    if oldest_date is None:
        return None
    return max(0, (reference_date - oldest_date).days)


def _calculator_slo_bucket(
    health: JobHealthSummary,
    *,
    reference_date: date,
) -> CalculatorSloBucket:
    return CalculatorSloBucket(
        pending_jobs=health.pending_jobs,
        processing_jobs=health.processing_jobs,
        stale_processing_jobs=health.stale_processing_jobs,
        failed_jobs=health.failed_jobs,
        failed_jobs_within_window=health.failed_jobs_last_hours,
        oldest_open_job_date=health.oldest_open_job_date,
        oldest_open_job_id=health.oldest_open_job_id,
        oldest_open_job_correlation_id=health.oldest_open_job_correlation_id,
        backlog_age_days=_backlog_age_days(
            health.oldest_open_job_date,
            reference_date=reference_date,
        ),
    )


def _reprocessing_slo_bucket(
    health: ReprocessingHealthSummary,
    *,
    reference_date: date,
) -> ReprocessingSloBucket:
    return ReprocessingSloBucket(
        active_reprocessing_keys=health.active_keys,
        stale_reprocessing_keys=health.stale_reprocessing_keys,
        oldest_reprocessing_watermark_date=health.oldest_reprocessing_watermark_date,
        oldest_reprocessing_security_id=health.oldest_reprocessing_security_id,
        oldest_reprocessing_epoch=health.oldest_reprocessing_epoch,
        oldest_reprocessing_updated_at=health.oldest_reprocessing_updated_at,
        backlog_age_days=_backlog_age_days(
            health.oldest_reprocessing_watermark_date,
            reference_date=reference_date,
        ),
    )


def build_calculator_slo_response(
    *,
    portfolio_id: str,
    latest_business_date: date | None,
    stale_threshold_minutes: int,
    failed_window_hours: int,
    generated_at_utc: datetime,
    reprocessing_health: ReprocessingHealthSummary,
    valuation_job_health: JobHealthSummary,
    aggregation_job_health: JobHealthSummary,
) -> CalculatorSloResponse:
    reference_date = latest_business_date or generated_at_utc.date()
    return CalculatorSloResponse(
        portfolio_id=portfolio_id,
        business_date=latest_business_date,
        stale_threshold_minutes=stale_threshold_minutes,
        failed_window_hours=failed_window_hours,
        generated_at_utc=generated_at_utc,
        valuation=_calculator_slo_bucket(
            valuation_job_health,
            reference_date=reference_date,
        ),
        aggregation=_calculator_slo_bucket(
            aggregation_job_health,
            reference_date=reference_date,
        ),
        reprocessing=_reprocessing_slo_bucket(
            reprocessing_health,
            reference_date=reference_date,
        ),
    )
