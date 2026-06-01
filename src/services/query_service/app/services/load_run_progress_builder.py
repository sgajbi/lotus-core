from datetime import date, datetime, timedelta

from portfolio_common.timeseries_constants import (
    DEPENDENT_POSITION_TIMESERIES_PROPAGATION_ROW_CAP,
)
from portfolio_common.valuation_runtime_settings import get_valuation_runtime_settings

from ..dtos.operations_dto import LoadRunProgressResponse
from ..repositories.operations_models import LoadRunProgressSummary
from ..support_policy import DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES

_VALUATION_RUNTIME_SETTINGS = get_valuation_runtime_settings()
VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS = (
    _VALUATION_RUNTIME_SETTINGS.valuation_scheduler_poll_interval_seconds
)
VALUATION_SCHEDULER_MAX_DISPATCH_JOBS_PER_POLL = (
    _VALUATION_RUNTIME_SETTINGS.valuation_scheduler_batch_size
    * _VALUATION_RUNTIME_SETTINGS.valuation_scheduler_dispatch_rounds
)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _non_negative_gap(upstream_count: int, downstream_count: int) -> int:
    return max(upstream_count - downstream_count, 0)


def _ceiling_division(numerator: int, denominator: int) -> int:
    if numerator <= 0 or denominator <= 0:
        return 0
    return (numerator + denominator - 1) // denominator


def _elapsed_seconds_between(
    older_timestamp: datetime | None,
    newer_timestamp: datetime | None,
) -> float | None:
    if older_timestamp is None or newer_timestamp is None:
        return None
    return round(max((newer_timestamp - older_timestamp).total_seconds(), 0.0), 6)


def get_load_run_state(summary: LoadRunProgressSummary) -> str:
    if summary.failed_valuation_jobs > 0 or summary.failed_aggregation_jobs > 0:
        return "FAILED"
    if (
        summary.portfolios_ingested > 0
        and summary.portfolios_with_timeseries == summary.portfolios_ingested
        and summary.open_valuation_jobs == 0
        and summary.open_aggregation_jobs == 0
    ):
        return "COMPLETE"
    if summary.portfolios_ingested > 0 and summary.transactions_ingested == 0:
        return "SEEDING"
    return "MATERIALIZING"


def _latest_load_run_activity_at(summary: LoadRunProgressSummary) -> datetime | None:
    activity_timestamps = [
        summary.latest_snapshot_materialized_at_utc,
        summary.latest_position_timeseries_materialized_at_utc,
        summary.latest_portfolio_timeseries_materialized_at_utc,
        summary.latest_valuation_job_updated_at_utc,
        summary.latest_aggregation_job_updated_at_utc,
    ]
    resolved_timestamps = [
        activity_timestamp
        for activity_timestamp in activity_timestamps
        if activity_timestamp is not None
    ]
    return max(resolved_timestamps) if resolved_timestamps else None


def get_load_run_operator_progress_state(
    summary: LoadRunProgressSummary,
    *,
    reference_now: datetime,
    stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
) -> str:
    run_state = get_load_run_state(summary)
    if run_state in {"FAILED", "COMPLETE"}:
        return run_state
    latest_activity_at = _latest_load_run_activity_at(summary)
    has_fresh_activity = latest_activity_at is not None and latest_activity_at >= (
        reference_now - timedelta(minutes=stale_threshold_minutes)
    )
    has_open_jobs = summary.open_valuation_jobs > 0 or summary.open_aggregation_jobs > 0
    if has_open_jobs and has_fresh_activity:
        return "RUNNING"
    if has_fresh_activity:
        return "SLOW"
    return "STUCK"


def _get_valuation_to_timeseries_handoff_pressure_hint(
    summary: LoadRunProgressSummary,
) -> str:
    if (
        summary.pending_valuation_jobs <= 0
        and summary.completed_valuation_jobs_without_position_timeseries <= 0
    ):
        return "NO_HANDOFF_PRESSURE"
    if (
        summary.pending_valuation_jobs > 0
        and summary.completed_valuation_jobs_without_position_timeseries <= 0
    ):
        return "SCHEDULER_DISPATCH_BOUND"
    if (
        summary.pending_valuation_jobs <= 0
        and summary.completed_valuation_jobs_without_position_timeseries > 0
    ):
        return "DOWNSTREAM_OF_VALUATION"
    return "MIXED_HANDOFF_PRESSURE"


def build_load_run_progress_response(
    *,
    run_id: str,
    business_date: date,
    generated_at_utc: datetime,
    summary: LoadRunProgressSummary,
) -> LoadRunProgressResponse:
    valuation_pending_dispatch_polls_lower_bound = _ceiling_division(
        summary.pending_valuation_jobs,
        VALUATION_SCHEDULER_MAX_DISPATCH_JOBS_PER_POLL,
    )
    return LoadRunProgressResponse(
        run_id=run_id,
        business_date=business_date,
        generated_at_utc=generated_at_utc,
        run_state=get_load_run_state(summary),
        operator_progress_stale_threshold_minutes=DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        operator_progress_state=get_load_run_operator_progress_state(
            summary,
            reference_now=generated_at_utc,
            stale_threshold_minutes=DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        ),
        portfolios_ingested=summary.portfolios_ingested,
        transactions_ingested=summary.transactions_ingested,
        portfolios_with_snapshots=summary.portfolios_with_snapshots,
        snapshot_rows=summary.snapshot_rows,
        portfolios_with_position_timeseries=summary.portfolios_with_position_timeseries,
        position_timeseries_rows=summary.position_timeseries_rows,
        portfolios_with_timeseries=summary.portfolios_with_timeseries,
        timeseries_rows=summary.timeseries_rows,
        complete_portfolios=summary.portfolios_with_timeseries,
        incomplete_portfolios=_non_negative_gap(
            summary.portfolios_ingested,
            summary.portfolios_with_timeseries,
        ),
        portfolios_waiting_for_snapshots=_non_negative_gap(
            summary.portfolios_ingested,
            summary.portfolios_with_snapshots,
        ),
        remaining_snapshot_rows=_non_negative_gap(
            summary.transactions_ingested,
            summary.snapshot_rows,
        ),
        snapshot_portfolio_coverage_ratio=_safe_ratio(
            summary.portfolios_with_snapshots,
            summary.portfolios_ingested,
        ),
        snapshot_portfolios_without_position_timeseries=_non_negative_gap(
            summary.portfolios_with_snapshots,
            summary.portfolios_with_position_timeseries,
        ),
        portfolios_waiting_for_position_timeseries=_non_negative_gap(
            summary.portfolios_with_snapshots,
            summary.portfolios_with_position_timeseries,
        ),
        remaining_position_timeseries_rows=_non_negative_gap(
            summary.transactions_ingested,
            summary.position_timeseries_rows,
        ),
        position_timeseries_portfolio_coverage_ratio=_safe_ratio(
            summary.portfolios_with_position_timeseries,
            summary.portfolios_ingested,
        ),
        position_timeseries_portfolios_without_portfolio_timeseries=_non_negative_gap(
            summary.portfolios_with_position_timeseries,
            summary.portfolios_with_timeseries,
        ),
        portfolios_waiting_for_portfolio_timeseries=_non_negative_gap(
            summary.portfolios_with_position_timeseries,
            summary.portfolios_with_timeseries,
        ),
        remaining_portfolio_timeseries_rows=_non_negative_gap(
            summary.portfolios_ingested,
            summary.timeseries_rows,
        ),
        timeseries_portfolio_coverage_ratio=_safe_ratio(
            summary.portfolios_with_timeseries,
            summary.portfolios_ingested,
        ),
        pending_valuation_jobs=summary.pending_valuation_jobs,
        processing_valuation_jobs=summary.processing_valuation_jobs,
        open_valuation_jobs=summary.open_valuation_jobs,
        pending_aggregation_jobs=summary.pending_aggregation_jobs,
        processing_aggregation_jobs=summary.processing_aggregation_jobs,
        open_aggregation_jobs=summary.open_aggregation_jobs,
        failed_valuation_jobs=summary.failed_valuation_jobs,
        failed_aggregation_jobs=summary.failed_aggregation_jobs,
        dependent_position_timeseries_propagation_row_cap=(
            DEPENDENT_POSITION_TIMESERIES_PROPAGATION_ROW_CAP
        ),
        valuation_scheduler_poll_interval_seconds=VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS,
        valuation_scheduler_max_dispatch_jobs_per_poll=(
            VALUATION_SCHEDULER_MAX_DISPATCH_JOBS_PER_POLL
        ),
        valuation_scheduler_pending_dispatch_polls_lower_bound=(
            valuation_pending_dispatch_polls_lower_bound
        ),
        valuation_scheduler_pending_dispatch_time_lower_bound_seconds=(
            valuation_pending_dispatch_polls_lower_bound * VALUATION_SCHEDULER_POLL_INTERVAL_SECONDS
        ),
        valuation_to_position_timeseries_handoff_pressure_hint=(
            _get_valuation_to_timeseries_handoff_pressure_hint(summary)
        ),
        oldest_pending_valuation_date=summary.oldest_pending_valuation_date,
        oldest_pending_aggregation_date=summary.oldest_pending_aggregation_date,
        latest_snapshot_date=summary.latest_snapshot_date,
        latest_timeseries_date=summary.latest_timeseries_date,
        latest_snapshot_materialized_at_utc=summary.latest_snapshot_materialized_at_utc,
        latest_valuation_to_snapshot_tail_seconds=_elapsed_seconds_between(
            summary.latest_valuation_job_updated_at_utc,
            summary.latest_snapshot_materialized_at_utc,
        ),
        latest_position_timeseries_materialized_at_utc=(
            summary.latest_position_timeseries_materialized_at_utc
        ),
        latest_valuation_to_position_timeseries_tail_seconds=_elapsed_seconds_between(
            summary.latest_valuation_job_updated_at_utc,
            summary.latest_position_timeseries_materialized_at_utc,
        ),
        latest_snapshot_to_position_timeseries_tail_seconds=_elapsed_seconds_between(
            summary.latest_snapshot_materialized_at_utc,
            summary.latest_position_timeseries_materialized_at_utc,
        ),
        latest_portfolio_timeseries_materialized_at_utc=(
            summary.latest_portfolio_timeseries_materialized_at_utc
        ),
        latest_position_timeseries_to_portfolio_timeseries_tail_seconds=(
            _elapsed_seconds_between(
                summary.latest_position_timeseries_materialized_at_utc,
                summary.latest_portfolio_timeseries_materialized_at_utc,
            )
        ),
        latest_valuation_job_updated_at_utc=summary.latest_valuation_job_updated_at_utc,
        latest_aggregation_job_updated_at_utc=summary.latest_aggregation_job_updated_at_utc,
        completed_valuation_jobs_without_position_timeseries=(
            summary.completed_valuation_jobs_without_position_timeseries
        ),
        completed_valuation_portfolios_without_position_timeseries=(
            summary.completed_valuation_portfolios_without_position_timeseries
        ),
        completed_valuation_portfolios_without_position_timeseries_ratio=_safe_ratio(
            summary.completed_valuation_portfolios_without_position_timeseries,
            summary.portfolios_ingested,
        ),
        completed_valuation_jobs_without_position_timeseries_per_affected_portfolio=(
            _safe_ratio(
                summary.completed_valuation_jobs_without_position_timeseries,
                summary.completed_valuation_portfolios_without_position_timeseries,
            )
        ),
        max_completed_valuation_jobs_without_position_timeseries_single_portfolio=(
            summary.max_completed_valuation_jobs_without_position_timeseries_single_portfolio
        ),
        dependent_position_timeseries_propagation_cap_risk=(
            summary.max_completed_valuation_jobs_without_position_timeseries_single_portfolio
            >= DEPENDENT_POSITION_TIMESERIES_PROPAGATION_ROW_CAP
        ),
        oldest_completed_valuation_without_position_timeseries_at_utc=(
            summary.oldest_completed_valuation_without_position_timeseries_at_utc
        ),
        oldest_completed_valuation_without_position_timeseries_age_seconds=(
            _elapsed_seconds_between(
                summary.oldest_completed_valuation_without_position_timeseries_at_utc,
                generated_at_utc,
            )
        ),
        valuation_to_position_timeseries_latency_sample_count=(
            summary.valuation_to_position_timeseries_latency_sample_count
        ),
        valuation_to_position_timeseries_latency_p50_seconds=(
            summary.valuation_to_position_timeseries_latency_p50_seconds
        ),
        valuation_to_position_timeseries_latency_p95_seconds=(
            summary.valuation_to_position_timeseries_latency_p95_seconds
        ),
        valuation_to_position_timeseries_latency_max_seconds=(
            summary.valuation_to_position_timeseries_latency_max_seconds
        ),
    )
