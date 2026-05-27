from datetime import date, datetime, timedelta, timezone

from src.services.query_service.app.repositories.operations_repository import (
    LoadRunProgressSummary,
)
from src.services.query_service.app.services.load_run_progress_builder import (
    build_load_run_progress_response,
    get_load_run_operator_progress_state,
)

GENERATED_AT = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


def _summary(**overrides: object) -> LoadRunProgressSummary:
    values = {
        "portfolios_ingested": 10,
        "transactions_ingested": 100,
        "portfolios_with_snapshots": 8,
        "snapshot_rows": 80,
        "portfolios_with_position_timeseries": 7,
        "position_timeseries_rows": 70,
        "portfolios_with_timeseries": 6,
        "timeseries_rows": 6,
        "pending_valuation_jobs": 3,
        "processing_valuation_jobs": 1,
        "open_valuation_jobs": 4,
        "pending_aggregation_jobs": 2,
        "processing_aggregation_jobs": 1,
        "open_aggregation_jobs": 3,
        "failed_valuation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "oldest_pending_valuation_date": date(2026, 5, 25),
        "oldest_pending_aggregation_date": date(2026, 5, 26),
        "latest_snapshot_date": date(2026, 5, 27),
        "latest_timeseries_date": date(2026, 5, 27),
        "latest_snapshot_materialized_at_utc": GENERATED_AT - timedelta(minutes=20),
        "latest_position_timeseries_materialized_at_utc": GENERATED_AT - timedelta(minutes=10),
        "latest_portfolio_timeseries_materialized_at_utc": GENERATED_AT - timedelta(minutes=5),
        "latest_valuation_job_updated_at_utc": GENERATED_AT - timedelta(minutes=25),
        "latest_aggregation_job_updated_at_utc": GENERATED_AT - timedelta(minutes=3),
        "completed_valuation_jobs_without_position_timeseries": 14,
        "completed_valuation_portfolios_without_position_timeseries": 2,
        "max_completed_valuation_jobs_without_position_timeseries_single_portfolio": 9,
        "oldest_completed_valuation_without_position_timeseries_at_utc": (
            GENERATED_AT - timedelta(minutes=45)
        ),
        "valuation_to_position_timeseries_latency_sample_count": 20,
        "valuation_to_position_timeseries_latency_p50_seconds": 30.0,
        "valuation_to_position_timeseries_latency_p95_seconds": 90.0,
        "valuation_to_position_timeseries_latency_max_seconds": 180.0,
    }
    values.update(overrides)
    return LoadRunProgressSummary(**values)


def test_build_load_run_progress_response_derives_operator_metrics():
    response = build_load_run_progress_response(
        run_id="RUN1",
        business_date=date(2026, 5, 27),
        generated_at_utc=GENERATED_AT,
        summary=_summary(),
    )

    assert response.run_state == "MATERIALIZING"
    assert response.operator_progress_state == "RUNNING"
    assert response.complete_portfolios == 6
    assert response.incomplete_portfolios == 4
    assert response.snapshot_portfolio_coverage_ratio == 0.8
    assert response.position_timeseries_portfolio_coverage_ratio == 0.7
    assert response.timeseries_portfolio_coverage_ratio == 0.6
    assert response.completed_valuation_jobs_without_position_timeseries_per_affected_portfolio == 7
    assert response.latest_valuation_to_snapshot_tail_seconds == 300
    assert response.latest_snapshot_to_position_timeseries_tail_seconds == 600
    assert response.oldest_completed_valuation_without_position_timeseries_age_seconds == 2700
    assert response.valuation_to_position_timeseries_handoff_pressure_hint == (
        "MIXED_HANDOFF_PRESSURE"
    )


def test_build_load_run_progress_response_bounds_empty_ratios():
    response = build_load_run_progress_response(
        run_id="RUN-SEED",
        business_date=date(2026, 5, 27),
        generated_at_utc=GENERATED_AT,
        summary=_summary(
            portfolios_ingested=5,
            transactions_ingested=0,
            portfolios_with_snapshots=0,
            snapshot_rows=0,
            portfolios_with_position_timeseries=0,
            position_timeseries_rows=0,
            portfolios_with_timeseries=0,
            timeseries_rows=0,
            pending_valuation_jobs=0,
            processing_valuation_jobs=0,
            open_valuation_jobs=0,
            pending_aggregation_jobs=0,
            processing_aggregation_jobs=0,
            open_aggregation_jobs=0,
            completed_valuation_jobs_without_position_timeseries=0,
            completed_valuation_portfolios_without_position_timeseries=0,
        ),
    )

    assert response.run_state == "SEEDING"
    assert response.snapshot_portfolio_coverage_ratio == 0
    assert response.completed_valuation_jobs_without_position_timeseries_per_affected_portfolio == 0
    assert response.valuation_to_position_timeseries_handoff_pressure_hint == "NO_HANDOFF_PRESSURE"


def test_get_load_run_operator_progress_state_covers_terminal_and_stale_states():
    running_summary = _summary(latest_aggregation_job_updated_at_utc=GENERATED_AT)
    slow_summary = _summary(
        open_valuation_jobs=0,
        open_aggregation_jobs=0,
        latest_aggregation_job_updated_at_utc=GENERATED_AT,
    )
    stuck_summary = _summary(
        open_valuation_jobs=0,
        open_aggregation_jobs=0,
        latest_snapshot_materialized_at_utc=GENERATED_AT - timedelta(hours=1),
        latest_position_timeseries_materialized_at_utc=GENERATED_AT - timedelta(hours=1),
        latest_portfolio_timeseries_materialized_at_utc=GENERATED_AT - timedelta(hours=1),
        latest_valuation_job_updated_at_utc=GENERATED_AT - timedelta(hours=1),
        latest_aggregation_job_updated_at_utc=GENERATED_AT - timedelta(hours=1),
    )
    complete_summary = _summary(
        portfolios_with_timeseries=10,
        open_valuation_jobs=0,
        open_aggregation_jobs=0,
    )
    failed_summary = _summary(failed_valuation_jobs=1)

    assert get_load_run_operator_progress_state(
        running_summary,
        reference_now=GENERATED_AT,
    ) == "RUNNING"
    assert get_load_run_operator_progress_state(
        slow_summary,
        reference_now=GENERATED_AT,
    ) == "SLOW"
    assert get_load_run_operator_progress_state(
        stuck_summary,
        reference_now=GENERATED_AT,
    ) == "STUCK"
    assert get_load_run_operator_progress_state(
        complete_summary,
        reference_now=GENERATED_AT,
    ) == "COMPLETE"
    assert get_load_run_operator_progress_state(
        failed_summary,
        reference_now=GENERATED_AT,
    ) == "FAILED"
