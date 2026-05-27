from datetime import date, datetime, timezone

from src.services.query_service.app.repositories.operations_repository import (
    JobHealthSummary,
    ReprocessingHealthSummary,
)
from src.services.query_service.app.services.calculator_slo_builder import (
    build_calculator_slo_response,
)

GENERATED_AT = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


def _job_health(**overrides: object) -> JobHealthSummary:
    values = {
        "pending_jobs": 0,
        "processing_jobs": 0,
        "stale_processing_jobs": 0,
        "failed_jobs": 0,
        "failed_jobs_last_hours": 0,
        "oldest_open_job_date": None,
        "oldest_open_job_id": None,
        "oldest_open_job_correlation_id": None,
        "oldest_open_security_id": None,
    }
    values.update(overrides)
    return JobHealthSummary(**values)


def _reprocessing_health(**overrides: object) -> ReprocessingHealthSummary:
    values = {
        "active_keys": 0,
        "stale_reprocessing_keys": 0,
        "oldest_reprocessing_watermark_date": None,
        "oldest_reprocessing_security_id": None,
        "oldest_reprocessing_epoch": None,
        "oldest_reprocessing_updated_at": None,
    }
    values.update(overrides)
    return ReprocessingHealthSummary(**values)


def test_build_calculator_slo_response_derives_backlog_ages_from_business_date():
    response = build_calculator_slo_response(
        portfolio_id="P1",
        latest_business_date=date(2026, 5, 27),
        stale_threshold_minutes=15,
        failed_window_hours=48,
        generated_at_utc=GENERATED_AT,
        reprocessing_health=_reprocessing_health(
            active_keys=2,
            stale_reprocessing_keys=1,
            oldest_reprocessing_watermark_date=date(2026, 5, 20),
            oldest_reprocessing_security_id="SEC-US-IBM",
            oldest_reprocessing_epoch=4,
            oldest_reprocessing_updated_at=GENERATED_AT,
        ),
        valuation_job_health=_job_health(
            pending_jobs=7,
            processing_jobs=3,
            stale_processing_jobs=1,
            failed_jobs=4,
            failed_jobs_last_hours=2,
            oldest_open_job_date=date(2026, 5, 24),
            oldest_open_job_id=8802,
            oldest_open_job_correlation_id="corr-val-8802",
        ),
        aggregation_job_health=_job_health(
            pending_jobs=5,
            failed_jobs=1,
            failed_jobs_last_hours=1,
            oldest_open_job_date=date(2026, 5, 25),
            oldest_open_job_id=4402,
            oldest_open_job_correlation_id="corr-agg-4402",
        ),
    )

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2026, 5, 27)
    assert response.stale_threshold_minutes == 15
    assert response.failed_window_hours == 48
    assert response.valuation.pending_jobs == 7
    assert response.valuation.failed_jobs == 4
    assert response.valuation.failed_jobs_within_window == 2
    assert response.valuation.backlog_age_days == 3
    assert response.aggregation.pending_jobs == 5
    assert response.aggregation.failed_jobs == 1
    assert response.aggregation.backlog_age_days == 2
    assert response.reprocessing.active_reprocessing_keys == 2
    assert response.reprocessing.stale_reprocessing_keys == 1
    assert response.reprocessing.backlog_age_days == 7
    assert response.reprocessing.oldest_reprocessing_security_id == "SEC-US-IBM"


def test_build_calculator_slo_response_uses_generated_date_when_business_date_missing():
    response = build_calculator_slo_response(
        portfolio_id="P1",
        latest_business_date=None,
        stale_threshold_minutes=15,
        failed_window_hours=24,
        generated_at_utc=GENERATED_AT,
        reprocessing_health=_reprocessing_health(
            oldest_reprocessing_watermark_date=date(2026, 5, 26),
        ),
        valuation_job_health=_job_health(oldest_open_job_date=date(2026, 5, 25)),
        aggregation_job_health=_job_health(),
    )

    assert response.business_date is None
    assert response.valuation.backlog_age_days == 2
    assert response.aggregation.backlog_age_days is None
    assert response.reprocessing.backlog_age_days == 1
