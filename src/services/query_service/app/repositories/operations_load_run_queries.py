from __future__ import annotations

from datetime import date, datetime

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PortfolioValuationJob,
    PositionTimeseries,
    Transaction,
)
from sqlalchemy import and_, func, select

from .operations_health_queries import int_or_zero, seconds_or_none
from .operations_models import LoadRunProgressSummary
from .operations_position_scope_queries import (
    apply_load_run_artifact_scope,
    apply_load_run_job_scope,
    security_id_expr,
)


def load_run_progress_valuation_handoff_statements(
    *,
    portfolio_pattern: str,
    as_of: datetime | None,
    has_superseding_valuation_epoch,
):
    valuation_handoff_base = select(
        PortfolioValuationJob.portfolio_id.label("portfolio_id"),
        security_id_expr(PortfolioValuationJob.security_id).label("security_id"),
        PortfolioValuationJob.valuation_date.label("valuation_date"),
        PortfolioValuationJob.epoch.label("epoch"),
        PortfolioValuationJob.updated_at.label("valuation_completed_at_utc"),
    )
    valuation_handoff_base = apply_load_run_job_scope(
        valuation_handoff_base,
        PortfolioValuationJob,
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
    ).where(
        PortfolioValuationJob.status == "COMPLETE",
        ~has_superseding_valuation_epoch,
    )
    valuation_handoff_subq = valuation_handoff_base.subquery()
    valuation_to_position_join = and_(
        PositionTimeseries.portfolio_id == valuation_handoff_subq.c.portfolio_id,
        security_id_expr(PositionTimeseries.security_id) == valuation_handoff_subq.c.security_id,
        PositionTimeseries.date == valuation_handoff_subq.c.valuation_date,
        PositionTimeseries.epoch == valuation_handoff_subq.c.epoch,
    )
    if as_of is not None:
        valuation_to_position_join = and_(
            valuation_to_position_join,
            PositionTimeseries.created_at <= as_of,
        )
    valuation_to_position_latency_seconds = func.greatest(
        func.extract(
            "epoch",
            PositionTimeseries.created_at - valuation_handoff_subq.c.valuation_completed_at_utc,
        ),
        0,
    )
    valuation_handoff_latency_stmt = (
        select(
            func.count(),
            func.percentile_cont(0.5).within_group(valuation_to_position_latency_seconds),
            func.percentile_cont(0.95).within_group(valuation_to_position_latency_seconds),
            func.max(valuation_to_position_latency_seconds),
        )
        .select_from(valuation_handoff_subq)
        .join(
            PositionTimeseries,
            valuation_to_position_join,
        )
    )
    valuation_without_position_timeseries_stmt = (
        select(
            func.count(),
            func.count(func.distinct(valuation_handoff_subq.c.portfolio_id)),
            func.min(valuation_handoff_subq.c.valuation_completed_at_utc),
        )
        .select_from(valuation_handoff_subq)
        .outerjoin(
            PositionTimeseries,
            valuation_to_position_join,
        )
        .where(PositionTimeseries.portfolio_id.is_(None))
    )
    valuation_without_position_timeseries_by_portfolio_subq = (
        select(
            valuation_handoff_subq.c.portfolio_id.label("portfolio_id"),
            func.count().label("waiting_count"),
        )
        .select_from(valuation_handoff_subq)
        .outerjoin(
            PositionTimeseries,
            valuation_to_position_join,
        )
        .where(PositionTimeseries.portfolio_id.is_(None))
        .group_by(valuation_handoff_subq.c.portfolio_id)
        .subquery()
    )
    max_waiting_portfolio_depth_stmt = select(
        func.max(valuation_without_position_timeseries_by_portfolio_subq.c.waiting_count)
    )
    return (
        valuation_handoff_latency_stmt,
        valuation_without_position_timeseries_stmt,
        max_waiting_portfolio_depth_stmt,
    )


def load_run_progress_scalar_statements(
    *,
    portfolio_pattern: str,
    transaction_pattern: str,
    business_date: date,
    as_of: datetime | None,
    has_superseding_valuation_epoch,
):
    portfolio_stmt = (
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.portfolio_id.like(portfolio_pattern))
    )
    transaction_stmt = (
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.transaction_id.like(transaction_pattern))
    )
    snapshot_portfolios_stmt = apply_load_run_artifact_scope(
        select(func.count(func.distinct(DailyPositionSnapshot.portfolio_id))),
        DailyPositionSnapshot,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    snapshot_rows_stmt = apply_load_run_artifact_scope(
        select(func.count()).select_from(DailyPositionSnapshot),
        DailyPositionSnapshot,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    position_timeseries_portfolios_stmt = apply_load_run_artifact_scope(
        select(func.count(func.distinct(PositionTimeseries.portfolio_id))),
        PositionTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    position_timeseries_rows_stmt = apply_load_run_artifact_scope(
        select(func.count()).select_from(PositionTimeseries),
        PositionTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    timeseries_portfolios_stmt = apply_load_run_artifact_scope(
        select(func.count(func.distinct(PortfolioTimeseries.portfolio_id))),
        PortfolioTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    timeseries_rows_stmt = apply_load_run_artifact_scope(
        select(func.count()).select_from(PortfolioTimeseries),
        PortfolioTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    (
        _valuation_handoff_latency_stmt,
        _valuation_without_position_timeseries_stmt,
        max_waiting_portfolio_depth_stmt,
    ) = load_run_progress_valuation_handoff_statements(
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
        has_superseding_valuation_epoch=has_superseding_valuation_epoch,
    )
    latest_snapshot_stmt = apply_load_run_artifact_scope(
        select(func.max(DailyPositionSnapshot.date)),
        DailyPositionSnapshot,
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
    )
    latest_snapshot_materialized_stmt = apply_load_run_artifact_scope(
        select(func.max(DailyPositionSnapshot.created_at)),
        DailyPositionSnapshot,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    latest_position_timeseries_materialized_stmt = apply_load_run_artifact_scope(
        select(func.max(PositionTimeseries.created_at)),
        PositionTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    latest_timeseries_stmt = apply_load_run_artifact_scope(
        select(func.max(PortfolioTimeseries.date)),
        PortfolioTimeseries,
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
    )
    latest_portfolio_timeseries_materialized_stmt = apply_load_run_artifact_scope(
        select(func.max(PortfolioTimeseries.created_at)),
        PortfolioTimeseries,
        portfolio_pattern=portfolio_pattern,
        business_date=business_date,
        as_of=as_of,
    )
    return (
        portfolio_stmt,
        transaction_stmt,
        snapshot_portfolios_stmt,
        snapshot_rows_stmt,
        position_timeseries_portfolios_stmt,
        position_timeseries_rows_stmt,
        timeseries_portfolios_stmt,
        timeseries_rows_stmt,
        max_waiting_portfolio_depth_stmt,
        latest_snapshot_stmt,
        latest_snapshot_materialized_stmt,
        latest_position_timeseries_materialized_stmt,
        latest_timeseries_stmt,
        latest_portfolio_timeseries_materialized_stmt,
    )


def load_run_progress_execute_statements(
    *,
    portfolio_pattern: str,
    as_of: datetime | None,
    actionable_valuation_job,
    has_superseding_valuation_epoch,
):
    valuation_base = select(
        PortfolioValuationJob.status.label("status"),
        PortfolioValuationJob.valuation_date.label("valuation_date"),
        PortfolioValuationJob.updated_at.label("updated_at"),
    )
    valuation_base = apply_load_run_job_scope(
        valuation_base,
        PortfolioValuationJob,
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
    ).where(actionable_valuation_job)
    valuation_subq = valuation_base.subquery()

    aggregation_base = select(
        PortfolioAggregationJob.status.label("status"),
        PortfolioAggregationJob.aggregation_date.label("aggregation_date"),
        PortfolioAggregationJob.updated_at.label("updated_at"),
    )
    aggregation_base = apply_load_run_job_scope(
        aggregation_base,
        PortfolioAggregationJob,
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
    )
    aggregation_subq = aggregation_base.subquery()

    valuation_summary_stmt = select(
        func.count().filter(valuation_subq.c.status == "PENDING"),
        func.count().filter(valuation_subq.c.status == "PROCESSING"),
        func.count().filter(valuation_subq.c.status == "FAILED"),
        func.min(valuation_subq.c.valuation_date).filter(
            valuation_subq.c.status.in_(("PENDING", "PROCESSING"))
        ),
        func.max(valuation_subq.c.updated_at),
    )
    aggregation_summary_stmt = select(
        func.count().filter(aggregation_subq.c.status == "PENDING"),
        func.count().filter(aggregation_subq.c.status == "PROCESSING"),
        func.count().filter(aggregation_subq.c.status == "FAILED"),
        func.min(aggregation_subq.c.aggregation_date).filter(
            aggregation_subq.c.status.in_(("PENDING", "PROCESSING"))
        ),
        func.max(aggregation_subq.c.updated_at),
    )
    (
        valuation_handoff_latency_stmt,
        valuation_without_position_timeseries_stmt,
        _max_waiting_portfolio_depth_stmt,
    ) = load_run_progress_valuation_handoff_statements(
        portfolio_pattern=portfolio_pattern,
        as_of=as_of,
        has_superseding_valuation_epoch=has_superseding_valuation_epoch,
    )
    return (
        valuation_summary_stmt,
        aggregation_summary_stmt,
        valuation_handoff_latency_stmt,
        valuation_without_position_timeseries_stmt,
    )


def load_run_progress_summary_from_rows(
    *,
    scalar_values,
    valuation_summary,
    aggregation_summary,
    valuation_handoff_latency,
    valuation_without_position_timeseries,
) -> LoadRunProgressSummary:
    (
        portfolios_ingested,
        transactions_ingested,
        portfolios_with_snapshots,
        snapshot_rows,
        portfolios_with_position_timeseries,
        position_timeseries_rows,
        portfolios_with_timeseries,
        timeseries_rows,
        max_waiting_portfolio_depth,
        latest_snapshot_date,
        latest_snapshot_materialized_at_utc,
        latest_position_timeseries_materialized_at_utc,
        latest_timeseries_date,
        latest_portfolio_timeseries_materialized_at_utc,
    ) = scalar_values
    (
        pending_valuation_jobs,
        processing_valuation_jobs,
        failed_valuation_jobs,
        oldest_pending_valuation_date,
        latest_valuation_job_updated_at_utc,
    ) = valuation_summary
    (
        pending_aggregation_jobs,
        processing_aggregation_jobs,
        failed_aggregation_jobs,
        oldest_pending_aggregation_date,
        latest_aggregation_job_updated_at_utc,
    ) = aggregation_summary
    (
        valuation_to_position_timeseries_latency_sample_count,
        valuation_to_position_timeseries_latency_p50_seconds,
        valuation_to_position_timeseries_latency_p95_seconds,
        valuation_to_position_timeseries_latency_max_seconds,
    ) = valuation_handoff_latency
    (
        completed_valuation_jobs_without_position_timeseries,
        completed_valuation_portfolios_without_position_timeseries,
        oldest_completed_valuation_without_position_timeseries_at_utc,
    ) = valuation_without_position_timeseries
    open_valuation_jobs = int_or_zero(pending_valuation_jobs) + int_or_zero(
        processing_valuation_jobs
    )
    open_aggregation_jobs = int_or_zero(pending_aggregation_jobs) + int_or_zero(
        processing_aggregation_jobs
    )

    return LoadRunProgressSummary(
        portfolios_ingested=int_or_zero(portfolios_ingested),
        transactions_ingested=int_or_zero(transactions_ingested),
        portfolios_with_snapshots=int_or_zero(portfolios_with_snapshots),
        snapshot_rows=int_or_zero(snapshot_rows),
        portfolios_with_position_timeseries=int_or_zero(portfolios_with_position_timeseries),
        position_timeseries_rows=int_or_zero(position_timeseries_rows),
        portfolios_with_timeseries=int_or_zero(portfolios_with_timeseries),
        timeseries_rows=int_or_zero(timeseries_rows),
        pending_valuation_jobs=int_or_zero(pending_valuation_jobs),
        processing_valuation_jobs=int_or_zero(processing_valuation_jobs),
        open_valuation_jobs=open_valuation_jobs,
        pending_aggregation_jobs=int_or_zero(pending_aggregation_jobs),
        processing_aggregation_jobs=int_or_zero(processing_aggregation_jobs),
        open_aggregation_jobs=open_aggregation_jobs,
        failed_valuation_jobs=int_or_zero(failed_valuation_jobs),
        failed_aggregation_jobs=int_or_zero(failed_aggregation_jobs),
        oldest_pending_valuation_date=oldest_pending_valuation_date,
        oldest_pending_aggregation_date=oldest_pending_aggregation_date,
        latest_snapshot_date=latest_snapshot_date,
        latest_timeseries_date=latest_timeseries_date,
        latest_snapshot_materialized_at_utc=latest_snapshot_materialized_at_utc,
        latest_position_timeseries_materialized_at_utc=(
            latest_position_timeseries_materialized_at_utc
        ),
        latest_portfolio_timeseries_materialized_at_utc=(
            latest_portfolio_timeseries_materialized_at_utc
        ),
        latest_valuation_job_updated_at_utc=latest_valuation_job_updated_at_utc,
        latest_aggregation_job_updated_at_utc=latest_aggregation_job_updated_at_utc,
        completed_valuation_jobs_without_position_timeseries=int_or_zero(
            completed_valuation_jobs_without_position_timeseries
        ),
        completed_valuation_portfolios_without_position_timeseries=int_or_zero(
            completed_valuation_portfolios_without_position_timeseries
        ),
        max_completed_valuation_jobs_without_position_timeseries_single_portfolio=int_or_zero(
            max_waiting_portfolio_depth
        ),
        oldest_completed_valuation_without_position_timeseries_at_utc=(
            oldest_completed_valuation_without_position_timeseries_at_utc
        ),
        valuation_to_position_timeseries_latency_sample_count=int_or_zero(
            valuation_to_position_timeseries_latency_sample_count
        ),
        valuation_to_position_timeseries_latency_p50_seconds=seconds_or_none(
            valuation_to_position_timeseries_latency_p50_seconds
        ),
        valuation_to_position_timeseries_latency_p95_seconds=seconds_or_none(
            valuation_to_position_timeseries_latency_p95_seconds
        ),
        valuation_to_position_timeseries_latency_max_seconds=seconds_or_none(
            valuation_to_position_timeseries_latency_max_seconds
        ),
    )
