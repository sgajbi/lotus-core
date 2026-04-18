from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    AnalyticsExportJob,
    BusinessDate,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    PipelineStageState,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    ReprocessingJob,
    Transaction,
)
from sqlalchemy import Date, and_, case, cast, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased


@dataclass(frozen=True)
class JobHealthSummary:
    pending_jobs: int
    processing_jobs: int
    stale_processing_jobs: int
    failed_jobs: int
    failed_jobs_last_hours: int
    oldest_open_job_date: Optional[date]
    oldest_open_job_id: Optional[int]
    oldest_open_job_correlation_id: Optional[str]
    oldest_open_security_id: Optional[str]


@dataclass(frozen=True)
class ExportJobHealthSummary:
    accepted_jobs: int
    running_jobs: int
    stale_running_jobs: int
    failed_jobs: int
    failed_jobs_last_hours: int
    oldest_open_job_created_at: Optional[datetime]
    oldest_open_job_id: Optional[str]
    oldest_open_request_fingerprint: Optional[str]


@dataclass(frozen=True)
class ReprocessingHealthSummary:
    active_keys: int
    stale_reprocessing_keys: int
    oldest_reprocessing_watermark_date: Optional[date]
    oldest_reprocessing_security_id: Optional[str]
    oldest_reprocessing_epoch: Optional[int]
    oldest_reprocessing_updated_at: Optional[datetime]


@dataclass(frozen=True)
class ReconciliationFindingSummary:
    total_findings: int
    blocking_findings: int
    top_blocking_finding_id: Optional[str]
    top_blocking_finding_type: Optional[str]
    top_blocking_finding_security_id: Optional[str]
    top_blocking_finding_transaction_id: Optional[str]


@dataclass(frozen=True)
class SnapshotValuationCoverageSummary:
    snapshot_date: Optional[date]
    total_positions: int
    valued_positions: int
    unvalued_positions: int


@dataclass(frozen=True)
class MissingHistoricalFxDependencyRecord:
    transaction_id: str
    security_id: str
    transaction_date: date
    trade_currency: str
    portfolio_currency: str


@dataclass(frozen=True)
class MissingHistoricalFxDependencySummary:
    missing_count: int
    earliest_transaction_date: Optional[date]
    latest_transaction_date: Optional[date]
    sample_records: list[MissingHistoricalFxDependencyRecord]


@dataclass(frozen=True)
class LoadRunProgressSummary:
    portfolios_ingested: int
    transactions_ingested: int
    portfolios_with_snapshots: int
    snapshot_rows: int
    portfolios_with_position_timeseries: int
    position_timeseries_rows: int
    portfolios_with_timeseries: int
    timeseries_rows: int
    pending_valuation_jobs: int
    processing_valuation_jobs: int
    open_valuation_jobs: int
    pending_aggregation_jobs: int
    processing_aggregation_jobs: int
    open_aggregation_jobs: int
    failed_valuation_jobs: int
    failed_aggregation_jobs: int
    oldest_pending_valuation_date: Optional[date]
    oldest_pending_aggregation_date: Optional[date]
    latest_snapshot_date: Optional[date]
    latest_timeseries_date: Optional[date]
    latest_snapshot_materialized_at_utc: Optional[datetime]
    latest_position_timeseries_materialized_at_utc: Optional[datetime]
    latest_portfolio_timeseries_materialized_at_utc: Optional[datetime]
    latest_valuation_job_updated_at_utc: Optional[datetime]
    latest_aggregation_job_updated_at_utc: Optional[datetime]
    completed_valuation_jobs_without_position_timeseries: int
    oldest_completed_valuation_without_position_timeseries_at_utc: Optional[datetime]
    valuation_to_position_timeseries_latency_sample_count: int
    valuation_to_position_timeseries_latency_p50_seconds: Optional[float]
    valuation_to_position_timeseries_latency_p95_seconds: Optional[float]
    valuation_to_position_timeseries_latency_max_seconds: Optional[float]


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _is_actionable_valuation_job(*, as_of: Optional[datetime] = None):
        superseding_job = aliased(PortfolioValuationJob)
        superseded_pending_exists = (
            select(superseding_job.id)
            .where(
                superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
                superseding_job.security_id == PortfolioValuationJob.security_id,
                superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
                superseding_job.epoch > PortfolioValuationJob.epoch,
            )
        )
        if as_of is not None:
            superseded_pending_exists = superseded_pending_exists.where(
                superseding_job.updated_at <= as_of
            )

        return case(
            (
                PortfolioValuationJob.status == "PENDING",
                ~superseded_pending_exists.exists(),
            ),
            else_=true(),
        )

    @staticmethod
    def _has_superseding_valuation_epoch(*, as_of: Optional[datetime] = None):
        superseding_job = aliased(PortfolioValuationJob)
        superseding_exists = select(superseding_job.id).where(
            superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
            superseding_job.security_id == PortfolioValuationJob.security_id,
            superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
            superseding_job.epoch > PortfolioValuationJob.epoch,
        )
        if as_of is not None:
            superseding_exists = superseding_exists.where(superseding_job.updated_at <= as_of)
        return superseding_exists.exists()

    @staticmethod
    def _reprocessing_job_portfolio_scope_exists(
        portfolio_id: str,
        security_id_expr,
        impacted_date_expr,
    ):
        latest_history = (
            select(
                PositionHistory.quantity.label("quantity"),
                func.row_number()
                .over(
                    partition_by=PositionHistory.portfolio_id,
                    order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == PositionHistory.portfolio_id,
                    PositionState.security_id == PositionHistory.security_id,
                    PositionState.epoch == PositionHistory.epoch,
                ),
            )
            .where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.security_id == security_id_expr,
                PositionHistory.security_id == security_id_expr,
                PositionHistory.position_date <= impacted_date_expr,
            )
            .correlate(ReprocessingJob)
            .subquery()
        )

        return (
            select(1)
            .select_from(latest_history)
            .where(latest_history.c.rn == 1, latest_history.c.quantity > 0)
            .exists()
        )

    @staticmethod
    def _support_job_priority(status_column, updated_at_column, stale_threshold: datetime):
        return case(
            (status_column == "FAILED", 0),
            (
                and_(status_column == "PROCESSING", updated_at_column < stale_threshold),
                1,
            ),
            (status_column == "PROCESSING", 2),
            (status_column == "PENDING", 3),
            else_=9,
        )

    @staticmethod
    def _analytics_export_job_priority(status_column, updated_at_column, stale_threshold: datetime):
        return case(
            (status_column == "failed", 0),
            (
                and_(status_column == "running", updated_at_column < stale_threshold),
                1,
            ),
            (status_column == "running", 2),
            (status_column == "accepted", 3),
            else_=9,
        )

    @staticmethod
    def _reconciliation_run_priority(status_column):
        return case(
            (status_column.in_(("FAILED", "REQUIRES_REPLAY")), 0),
            (status_column == "RUNNING", 1),
            else_=9,
        )

    @staticmethod
    def _portfolio_control_stage_priority(status_column):
        return case(
            (status_column.in_(("FAILED", "REQUIRES_REPLAY")), 0),
            else_=9,
        )

    @staticmethod
    def _reprocessing_key_priority(status_column, updated_at_column, stale_threshold: datetime):
        return case(
            (
                and_(status_column == "REPROCESSING", updated_at_column < stale_threshold),
                0,
            ),
            (status_column == "REPROCESSING", 1),
            else_=9,
        )

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def get_load_run_progress(
        self,
        run_id: str,
        business_date: date,
        as_of: Optional[datetime] = None,
    ) -> LoadRunProgressSummary:
        portfolio_pattern = f"LOAD_{run_id}_PF_%"
        transaction_pattern = f"LOAD_{run_id}_TX_%"

        portfolio_stmt = select(func.count()).select_from(Portfolio).where(
            Portfolio.portfolio_id.like(portfolio_pattern)
        )
        transaction_stmt = select(func.count()).select_from(Transaction).where(
            Transaction.transaction_id.like(transaction_pattern)
        )
        snapshot_portfolios_stmt = select(
            func.count(func.distinct(DailyPositionSnapshot.portfolio_id))
        ).where(
            DailyPositionSnapshot.portfolio_id.like(portfolio_pattern),
            DailyPositionSnapshot.date == business_date,
        )
        snapshot_rows_stmt = select(func.count()).select_from(DailyPositionSnapshot).where(
            DailyPositionSnapshot.portfolio_id.like(portfolio_pattern),
            DailyPositionSnapshot.date == business_date,
        )
        position_timeseries_portfolios_stmt = select(
            func.count(func.distinct(PositionTimeseries.portfolio_id))
        ).where(
            PositionTimeseries.portfolio_id.like(portfolio_pattern),
            PositionTimeseries.date == business_date,
        )
        position_timeseries_rows_stmt = select(func.count()).select_from(PositionTimeseries).where(
            PositionTimeseries.portfolio_id.like(portfolio_pattern),
            PositionTimeseries.date == business_date,
        )
        timeseries_portfolios_stmt = select(
            func.count(func.distinct(PortfolioTimeseries.portfolio_id))
        ).where(
            PortfolioTimeseries.portfolio_id.like(portfolio_pattern),
            PortfolioTimeseries.date == business_date,
        )
        timeseries_rows_stmt = select(func.count()).select_from(PortfolioTimeseries).where(
            PortfolioTimeseries.portfolio_id.like(portfolio_pattern),
            PortfolioTimeseries.date == business_date,
        )
        if as_of is not None:
            snapshot_portfolios_stmt = snapshot_portfolios_stmt.where(
                DailyPositionSnapshot.created_at <= as_of
            )
            snapshot_rows_stmt = snapshot_rows_stmt.where(DailyPositionSnapshot.created_at <= as_of)
            position_timeseries_portfolios_stmt = position_timeseries_portfolios_stmt.where(
                PositionTimeseries.created_at <= as_of
            )
            position_timeseries_rows_stmt = position_timeseries_rows_stmt.where(
                PositionTimeseries.created_at <= as_of
            )
            timeseries_portfolios_stmt = timeseries_portfolios_stmt.where(
                PortfolioTimeseries.created_at <= as_of
            )
            timeseries_rows_stmt = timeseries_rows_stmt.where(
                PortfolioTimeseries.created_at <= as_of
            )

        valuation_base = select(
            PortfolioValuationJob.status.label("status"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.updated_at.label("updated_at"),
        ).where(
            PortfolioValuationJob.portfolio_id.like(portfolio_pattern),
            self._is_actionable_valuation_job(as_of=as_of),
        )
        if as_of is not None:
            valuation_base = valuation_base.where(PortfolioValuationJob.updated_at <= as_of)
        valuation_subq = valuation_base.subquery()

        aggregation_base = select(
            PortfolioAggregationJob.status.label("status"),
            PortfolioAggregationJob.aggregation_date.label("aggregation_date"),
            PortfolioAggregationJob.updated_at.label("updated_at"),
        ).where(PortfolioAggregationJob.portfolio_id.like(portfolio_pattern))
        if as_of is not None:
            aggregation_base = aggregation_base.where(PortfolioAggregationJob.updated_at <= as_of)
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
        valuation_handoff_base = select(
            PortfolioValuationJob.portfolio_id.label("portfolio_id"),
            PortfolioValuationJob.security_id.label("security_id"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.epoch.label("epoch"),
            PortfolioValuationJob.updated_at.label("valuation_completed_at_utc"),
        ).where(
            PortfolioValuationJob.portfolio_id.like(portfolio_pattern),
            PortfolioValuationJob.status == "COMPLETE",
            ~self._has_superseding_valuation_epoch(as_of=as_of),
        )
        if as_of is not None:
            valuation_handoff_base = valuation_handoff_base.where(
                PortfolioValuationJob.updated_at <= as_of
            )
        valuation_handoff_subq = valuation_handoff_base.subquery()
        valuation_to_position_join = and_(
            PositionTimeseries.portfolio_id == valuation_handoff_subq.c.portfolio_id,
            PositionTimeseries.security_id == valuation_handoff_subq.c.security_id,
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
            0.0,
        )
        valuation_handoff_latency_stmt = select(
            func.count(),
            func.percentile_cont(0.5).within_group(valuation_to_position_latency_seconds),
            func.percentile_cont(0.95).within_group(valuation_to_position_latency_seconds),
            func.max(valuation_to_position_latency_seconds),
        ).select_from(valuation_handoff_subq).join(
            PositionTimeseries,
            valuation_to_position_join,
        )
        valuation_without_position_timeseries_stmt = select(
            func.count(),
            func.min(valuation_handoff_subq.c.valuation_completed_at_utc),
        ).select_from(valuation_handoff_subq).outerjoin(
            PositionTimeseries,
            valuation_to_position_join,
        ).where(PositionTimeseries.portfolio_id.is_(None))
        latest_snapshot_stmt = select(func.max(DailyPositionSnapshot.date)).where(
            DailyPositionSnapshot.portfolio_id.like(portfolio_pattern)
        )
        latest_snapshot_materialized_stmt = (
            select(func.max(DailyPositionSnapshot.created_at))
            .where(
                DailyPositionSnapshot.portfolio_id.like(portfolio_pattern),
                DailyPositionSnapshot.date == business_date,
            )
        )
        latest_position_timeseries_materialized_stmt = select(
            func.max(PositionTimeseries.created_at)
        ).where(
            PositionTimeseries.portfolio_id.like(portfolio_pattern),
            PositionTimeseries.date == business_date,
        )
        latest_timeseries_stmt = select(func.max(PortfolioTimeseries.date)).where(
            PortfolioTimeseries.portfolio_id.like(portfolio_pattern)
        )
        latest_portfolio_timeseries_materialized_stmt = select(
            func.max(PortfolioTimeseries.created_at)
        ).where(
            PortfolioTimeseries.portfolio_id.like(portfolio_pattern),
            PortfolioTimeseries.date == business_date,
        )
        if as_of is not None:
            latest_snapshot_stmt = latest_snapshot_stmt.where(
                DailyPositionSnapshot.created_at <= as_of
            )
            latest_snapshot_materialized_stmt = latest_snapshot_materialized_stmt.where(
                DailyPositionSnapshot.created_at <= as_of
            )
            latest_position_timeseries_materialized_stmt = (
                latest_position_timeseries_materialized_stmt.where(
                    PositionTimeseries.created_at <= as_of
                )
            )
            latest_timeseries_stmt = latest_timeseries_stmt.where(
                PortfolioTimeseries.created_at <= as_of
            )
            latest_portfolio_timeseries_materialized_stmt = (
                latest_portfolio_timeseries_materialized_stmt.where(
                    PortfolioTimeseries.created_at <= as_of
                )
            )

        portfolios_ingested = await self.db.scalar(portfolio_stmt)
        transactions_ingested = await self.db.scalar(transaction_stmt)
        portfolios_with_snapshots = await self.db.scalar(snapshot_portfolios_stmt)
        snapshot_rows = await self.db.scalar(snapshot_rows_stmt)
        portfolios_with_position_timeseries = await self.db.scalar(
            position_timeseries_portfolios_stmt
        )
        position_timeseries_rows = await self.db.scalar(position_timeseries_rows_stmt)
        portfolios_with_timeseries = await self.db.scalar(timeseries_portfolios_stmt)
        timeseries_rows = await self.db.scalar(timeseries_rows_stmt)
        valuation_summary = await self.db.execute(valuation_summary_stmt)
        aggregation_summary = await self.db.execute(aggregation_summary_stmt)
        valuation_handoff_latency = await self.db.execute(valuation_handoff_latency_stmt)
        valuation_without_position_timeseries = await self.db.execute(
            valuation_without_position_timeseries_stmt
        )
        latest_snapshot_date = await self.db.scalar(latest_snapshot_stmt)
        latest_snapshot_materialized_at_utc = await self.db.scalar(
            latest_snapshot_materialized_stmt
        )
        latest_position_timeseries_materialized_at_utc = await self.db.scalar(
            latest_position_timeseries_materialized_stmt
        )
        latest_timeseries_date = await self.db.scalar(latest_timeseries_stmt)
        latest_portfolio_timeseries_materialized_at_utc = await self.db.scalar(
            latest_portfolio_timeseries_materialized_stmt
        )
        (
            pending_valuation_jobs,
            processing_valuation_jobs,
            failed_valuation_jobs,
            oldest_pending_valuation_date,
            latest_valuation_job_updated_at_utc,
        ) = valuation_summary.one()
        (
            pending_aggregation_jobs,
            processing_aggregation_jobs,
            failed_aggregation_jobs,
            oldest_pending_aggregation_date,
            latest_aggregation_job_updated_at_utc,
        ) = aggregation_summary.one()
        (
            valuation_to_position_timeseries_latency_sample_count,
            valuation_to_position_timeseries_latency_p50_seconds,
            valuation_to_position_timeseries_latency_p95_seconds,
            valuation_to_position_timeseries_latency_max_seconds,
        ) = valuation_handoff_latency.one()
        (
            completed_valuation_jobs_without_position_timeseries,
            oldest_completed_valuation_without_position_timeseries_at_utc,
        ) = valuation_without_position_timeseries.one()
        open_valuation_jobs = int(pending_valuation_jobs or 0) + int(processing_valuation_jobs or 0)
        open_aggregation_jobs = int(pending_aggregation_jobs or 0) + int(
            processing_aggregation_jobs or 0
        )

        return LoadRunProgressSummary(
            portfolios_ingested=int(portfolios_ingested or 0),
            transactions_ingested=int(transactions_ingested or 0),
            portfolios_with_snapshots=int(portfolios_with_snapshots or 0),
            snapshot_rows=int(snapshot_rows or 0),
            portfolios_with_position_timeseries=int(portfolios_with_position_timeseries or 0),
            position_timeseries_rows=int(position_timeseries_rows or 0),
            portfolios_with_timeseries=int(portfolios_with_timeseries or 0),
            timeseries_rows=int(timeseries_rows or 0),
            pending_valuation_jobs=int(pending_valuation_jobs or 0),
            processing_valuation_jobs=int(processing_valuation_jobs or 0),
            open_valuation_jobs=open_valuation_jobs,
            pending_aggregation_jobs=int(pending_aggregation_jobs or 0),
            processing_aggregation_jobs=int(processing_aggregation_jobs or 0),
            open_aggregation_jobs=open_aggregation_jobs,
            failed_valuation_jobs=int(failed_valuation_jobs or 0),
            failed_aggregation_jobs=int(failed_aggregation_jobs or 0),
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
            completed_valuation_jobs_without_position_timeseries=int(
                completed_valuation_jobs_without_position_timeseries or 0
            ),
            oldest_completed_valuation_without_position_timeseries_at_utc=(
                oldest_completed_valuation_without_position_timeseries_at_utc
            ),
            valuation_to_position_timeseries_latency_sample_count=int(
                valuation_to_position_timeseries_latency_sample_count or 0
            ),
            valuation_to_position_timeseries_latency_p50_seconds=(
                float(valuation_to_position_timeseries_latency_p50_seconds)
                if valuation_to_position_timeseries_latency_p50_seconds is not None
                else None
            ),
            valuation_to_position_timeseries_latency_p95_seconds=(
                float(valuation_to_position_timeseries_latency_p95_seconds)
                if valuation_to_position_timeseries_latency_p95_seconds is not None
                else None
            ),
            valuation_to_position_timeseries_latency_max_seconds=(
                float(valuation_to_position_timeseries_latency_max_seconds)
                if valuation_to_position_timeseries_latency_max_seconds is not None
                else None
            ),
        )

    async def get_current_portfolio_epoch(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[int]:
        stmt = select(func.max(PositionState.epoch)).where(
            PositionState.portfolio_id == portfolio_id
        )
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_reprocessing_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> ReprocessingHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        base_stmt = select(
            PositionState.status.label("status"),
            PositionState.updated_at.label("updated_at"),
            PositionState.watermark_date.label("watermark_date"),
            PositionState.security_id.label("security_id"),
            PositionState.epoch.label("epoch"),
        ).where(PositionState.portfolio_id == portfolio_id)
        if as_of is not None:
            base_stmt = base_stmt.where(PositionState.updated_at <= as_of)
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count()
                .filter(base_subq.c.status == "REPROCESSING")
                .label("active_keys"),
                func.count()
                .filter(
                    base_subq.c.status == "REPROCESSING",
                    base_subq.c.updated_at < stale_threshold,
                )
                .label("stale_reprocessing_keys"),
                func.min(base_subq.c.watermark_date)
                .filter(base_subq.c.status == "REPROCESSING")
                .label("oldest_reprocessing_watermark_date"),
            )
            .select_from(base_subq)
            .subquery()
        )
        oldest_key_subq = (
            select(
                base_subq.c.security_id,
                base_subq.c.epoch,
                base_subq.c.updated_at,
            )
            .where(base_subq.c.status == "REPROCESSING")
            .order_by(
                base_subq.c.watermark_date.asc(),
                base_subq.c.updated_at.asc(),
                base_subq.c.security_id.asc(),
            )
            .limit(1)
            .subquery()
        )
        row = (
            await self.db.execute(
                select(
                    aggregate_subq.c.active_keys,
                    aggregate_subq.c.stale_reprocessing_keys,
                    aggregate_subq.c.oldest_reprocessing_watermark_date,
                    oldest_key_subq.c.security_id,
                    oldest_key_subq.c.epoch,
                    oldest_key_subq.c.updated_at,
                ).select_from(aggregate_subq).outerjoin(oldest_key_subq, true())
            )
        ).one()
        return ReprocessingHealthSummary(
            active_keys=int(row.active_keys or 0),
            stale_reprocessing_keys=int(row.stale_reprocessing_keys or 0),
            oldest_reprocessing_watermark_date=row.oldest_reprocessing_watermark_date,
            oldest_reprocessing_security_id=row.security_id,
            oldest_reprocessing_epoch=row.epoch,
            oldest_reprocessing_updated_at=row.updated_at,
        )

    async def get_valuation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> JobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        base_stmt = select(
            PortfolioValuationJob.status.label("status"),
            PortfolioValuationJob.updated_at.label("updated_at"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.id.label("id"),
            PortfolioValuationJob.correlation_id.label("correlation_id"),
            PortfolioValuationJob.security_id.label("security_id"),
        ).where(
            PortfolioValuationJob.portfolio_id == portfolio_id,
            self._is_actionable_valuation_job(as_of=as_of),
        )
        if as_of is not None:
            base_stmt = base_stmt.where(PortfolioValuationJob.updated_at <= as_of)
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count()
                .filter(base_subq.c.status.in_(("PENDING", "PROCESSING")))
                .label("pending_jobs"),
                func.count()
                .filter(base_subq.c.status == "PROCESSING")
                .label("processing_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "PROCESSING",
                    base_subq.c.updated_at < stale_threshold,
                )
                .label("stale_processing_jobs"),
                func.count().filter(base_subq.c.status == "FAILED").label("failed_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "FAILED",
                    base_subq.c.updated_at >= failed_since,
                )
                .label("failed_jobs_last_hours"),
                func.min(base_subq.c.valuation_date)
                .filter(base_subq.c.status.in_(("PENDING", "PROCESSING")))
                .label("oldest_open_job_date"),
            )
            .select_from(base_subq)
            .subquery()
        )
        oldest_job_subq = (
            select(
                base_subq.c.id,
                base_subq.c.security_id,
                base_subq.c.correlation_id,
            )
            .where(base_subq.c.status.in_(("PENDING", "PROCESSING")))
            .order_by(
                base_subq.c.valuation_date.asc(),
                base_subq.c.updated_at.asc(),
                base_subq.c.id.asc(),
            )
            .limit(1)
            .subquery()
        )
        row = (
            await self.db.execute(
                select(
                    aggregate_subq.c.pending_jobs,
                    aggregate_subq.c.processing_jobs,
                    aggregate_subq.c.stale_processing_jobs,
                    aggregate_subq.c.failed_jobs,
                    aggregate_subq.c.failed_jobs_last_hours,
                    aggregate_subq.c.oldest_open_job_date,
                    oldest_job_subq.c.id,
                    oldest_job_subq.c.security_id,
                    oldest_job_subq.c.correlation_id,
                ).select_from(aggregate_subq).outerjoin(oldest_job_subq, true())
            )
        ).one()
        return JobHealthSummary(
            pending_jobs=int(row.pending_jobs or 0),
            processing_jobs=int(row.processing_jobs or 0),
            stale_processing_jobs=int(row.stale_processing_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_date=row.oldest_open_job_date,
            oldest_open_job_id=row.id,
            oldest_open_job_correlation_id=row.correlation_id,
            oldest_open_security_id=row.security_id,
        )

    async def get_aggregation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> JobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        base_stmt = select(
            PortfolioAggregationJob.status.label("status"),
            PortfolioAggregationJob.updated_at.label("updated_at"),
            PortfolioAggregationJob.aggregation_date.label("aggregation_date"),
            PortfolioAggregationJob.id.label("id"),
            PortfolioAggregationJob.correlation_id.label("correlation_id"),
        ).where(PortfolioAggregationJob.portfolio_id == portfolio_id)
        if as_of is not None:
            base_stmt = base_stmt.where(PortfolioAggregationJob.updated_at <= as_of)
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count()
                .filter(base_subq.c.status.in_(("PENDING", "PROCESSING")))
                .label("pending_jobs"),
                func.count()
                .filter(base_subq.c.status == "PROCESSING")
                .label("processing_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "PROCESSING",
                    base_subq.c.updated_at < stale_threshold,
                )
                .label("stale_processing_jobs"),
                func.count().filter(base_subq.c.status == "FAILED").label("failed_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "FAILED",
                    base_subq.c.updated_at >= failed_since,
                )
                .label("failed_jobs_last_hours"),
                func.min(base_subq.c.aggregation_date)
                .filter(base_subq.c.status.in_(("PENDING", "PROCESSING")))
                .label("oldest_open_job_date"),
            )
            .select_from(base_subq)
            .subquery()
        )
        oldest_job_subq = (
            select(
                base_subq.c.id,
                base_subq.c.correlation_id,
            )
            .where(base_subq.c.status.in_(("PENDING", "PROCESSING")))
            .order_by(
                base_subq.c.aggregation_date.asc(),
                base_subq.c.updated_at.asc(),
                base_subq.c.id.asc(),
            )
            .limit(1)
            .subquery()
        )
        row = (
            await self.db.execute(
                select(
                    aggregate_subq.c.pending_jobs,
                    aggregate_subq.c.processing_jobs,
                    aggregate_subq.c.stale_processing_jobs,
                    aggregate_subq.c.failed_jobs,
                    aggregate_subq.c.failed_jobs_last_hours,
                    aggregate_subq.c.oldest_open_job_date,
                    oldest_job_subq.c.id,
                    oldest_job_subq.c.correlation_id,
                ).select_from(aggregate_subq).outerjoin(oldest_job_subq, true())
            )
        ).one()
        return JobHealthSummary(
            pending_jobs=int(row.pending_jobs or 0),
            processing_jobs=int(row.processing_jobs or 0),
            stale_processing_jobs=int(row.stale_processing_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_date=row.oldest_open_job_date,
            oldest_open_job_id=row.id,
            oldest_open_job_correlation_id=row.correlation_id,
            oldest_open_security_id=None,
        )

    async def get_analytics_export_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> ExportJobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        base_stmt = select(
            AnalyticsExportJob.status.label("status"),
            AnalyticsExportJob.updated_at.label("updated_at"),
            AnalyticsExportJob.created_at.label("created_at"),
            AnalyticsExportJob.job_id.label("job_id"),
            AnalyticsExportJob.request_fingerprint.label("request_fingerprint"),
        ).where(AnalyticsExportJob.portfolio_id == portfolio_id)
        if as_of is not None:
            base_stmt = base_stmt.where(AnalyticsExportJob.updated_at <= as_of)
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count().filter(base_subq.c.status == "accepted").label("accepted_jobs"),
                func.count().filter(base_subq.c.status == "running").label("running_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "running",
                    base_subq.c.updated_at < stale_threshold,
                )
                .label("stale_running_jobs"),
                func.count().filter(base_subq.c.status == "failed").label("failed_jobs"),
                func.count()
                .filter(
                    base_subq.c.status == "failed",
                    base_subq.c.updated_at >= failed_since,
                )
                .label("failed_jobs_last_hours"),
                func.min(base_subq.c.created_at)
                .filter(base_subq.c.status.in_(("accepted", "running")))
                .label("oldest_open_job_created_at"),
            )
            .select_from(base_subq)
            .subquery()
        )
        oldest_job_subq = (
            select(
                base_subq.c.job_id,
                base_subq.c.request_fingerprint,
            )
            .where(base_subq.c.status.in_(("accepted", "running")))
            .order_by(
                base_subq.c.created_at.asc(),
                base_subq.c.updated_at.asc(),
                base_subq.c.job_id.asc(),
            )
            .limit(1)
            .subquery()
        )
        row = (
            await self.db.execute(
                select(
                    aggregate_subq.c.accepted_jobs,
                    aggregate_subq.c.running_jobs,
                    aggregate_subq.c.stale_running_jobs,
                    aggregate_subq.c.failed_jobs,
                    aggregate_subq.c.failed_jobs_last_hours,
                    aggregate_subq.c.oldest_open_job_created_at,
                    oldest_job_subq.c.job_id,
                    oldest_job_subq.c.request_fingerprint,
                ).select_from(aggregate_subq).outerjoin(oldest_job_subq, true())
            )
        ).one()
        return ExportJobHealthSummary(
            accepted_jobs=int(row.accepted_jobs or 0),
            running_jobs=int(row.running_jobs or 0),
            stale_running_jobs=int(row.stale_running_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_created_at=row.oldest_open_job_created_at,
            oldest_open_job_id=row.job_id,
            oldest_open_request_fingerprint=row.request_fingerprint,
        )

    async def get_latest_transaction_date(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        stmt = select(func.max(func.date(Transaction.transaction_date))).where(
            Transaction.portfolio_id == portfolio_id
        )
        if as_of is not None:
            stmt = stmt.where(Transaction.created_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_transaction_date_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: Optional[datetime] = None,
    ) -> Optional[date]:
        stmt = select(func.max(func.date(Transaction.transaction_date))).where(
            Transaction.portfolio_id == portfolio_id,
            func.date(Transaction.transaction_date) <= as_of_date,
        )
        if snapshot_as_of is not None:
            stmt = stmt.where(Transaction.created_at <= snapshot_as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_business_date(self, as_of: Optional[datetime] = None) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        if as_of is not None:
            stmt = stmt.where(BusinessDate.created_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        stmt = (
            select(func.max(DailyPositionSnapshot.date))
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(
                DailyPositionSnapshot.created_at <= as_of,
                PositionState.updated_at <= as_of,
            )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: Optional[datetime] = None,
    ) -> Optional[date]:
        stmt = (
            select(func.max(DailyPositionSnapshot.date))
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= as_of_date,
            )
        )
        if snapshot_as_of is not None:
            stmt = stmt.where(
                DailyPositionSnapshot.created_at <= snapshot_as_of,
                PositionState.updated_at <= snapshot_as_of,
            )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_snapshot_history_mismatch_count(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> int:
        latest_history = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.security_id,
                PositionHistory.epoch,
                func.max(PositionHistory.position_date).label("latest_history_date"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    PositionHistory.security_id == PositionState.security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(PositionHistory.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            latest_history = latest_history.where(
                PositionHistory.created_at <= as_of,
                PositionState.updated_at <= as_of,
            )
        latest_history = latest_history.group_by(
            PositionHistory.portfolio_id, PositionHistory.security_id, PositionHistory.epoch
        ).subquery()
        latest_snapshot = (
            select(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.security_id,
                DailyPositionSnapshot.epoch,
                func.max(DailyPositionSnapshot.date).label("latest_snapshot_date"),
            )
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            latest_snapshot = latest_snapshot.where(
                DailyPositionSnapshot.created_at <= as_of,
                PositionState.updated_at <= as_of,
            )
        latest_snapshot = latest_snapshot.group_by(
            DailyPositionSnapshot.portfolio_id,
            DailyPositionSnapshot.security_id,
            DailyPositionSnapshot.epoch,
        ).subquery()
        joined = latest_history.outerjoin(
            latest_snapshot,
            and_(
                latest_history.c.portfolio_id == latest_snapshot.c.portfolio_id,
                latest_history.c.security_id == latest_snapshot.c.security_id,
                latest_history.c.epoch == latest_snapshot.c.epoch,
            ),
        )
        stmt = (
            select(func.count())
            .select_from(joined)
            .where(
                latest_snapshot.c.latest_snapshot_date.is_(None),
                latest_history.c.latest_history_date.is_not(None),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_snapshot_valuation_coverage_summary(
        self,
        portfolio_id: str,
        snapshot_date: Optional[date],
        snapshot_as_of: Optional[datetime] = None,
    ) -> SnapshotValuationCoverageSummary:
        if snapshot_date is None:
            return SnapshotValuationCoverageSummary(
                snapshot_date=None,
                total_positions=0,
                valued_positions=0,
                unvalued_positions=0,
            )

        stmt = (
            select(
                func.count().label("total_positions"),
                func.count()
                .filter(
                    DailyPositionSnapshot.valuation_status.is_not(None),
                    DailyPositionSnapshot.valuation_status != "UNVALUED",
                )
                .label("valued_positions"),
            )
            .select_from(DailyPositionSnapshot)
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date == snapshot_date,
            )
        )
        if snapshot_as_of is not None:
            stmt = stmt.where(
                DailyPositionSnapshot.created_at <= snapshot_as_of,
                PositionState.updated_at <= snapshot_as_of,
            )
        row = (await self.db.execute(stmt)).one()
        total_positions = int(row.total_positions or 0)
        valued_positions = int(row.valued_positions or 0)
        return SnapshotValuationCoverageSummary(
            snapshot_date=snapshot_date,
            total_positions=total_positions,
            valued_positions=valued_positions,
            unvalued_positions=max(total_positions - valued_positions, 0),
        )

    async def get_missing_historical_fx_dependency_summary(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: Optional[datetime] = None,
        sample_limit: int = 10,
    ) -> MissingHistoricalFxDependencySummary:
        base_stmt = (
            select(
                Transaction.transaction_id.label("transaction_id"),
                Transaction.security_id.label("security_id"),
                cast(func.date(Transaction.transaction_date), Date).label("transaction_date"),
                Transaction.trade_currency.label("trade_currency"),
                Portfolio.base_currency.label("portfolio_currency"),
            )
            .join(Portfolio, Portfolio.portfolio_id == Transaction.portfolio_id)
            .where(
                Transaction.portfolio_id == portfolio_id,
                cast(func.date(Transaction.transaction_date), Date) <= as_of_date,
                Transaction.trade_currency != Portfolio.base_currency,
                Transaction.transaction_fx_rate.is_(None),
            )
        )
        if snapshot_as_of is not None:
            base_stmt = base_stmt.where(Transaction.created_at <= snapshot_as_of)
        base_subq = base_stmt.subquery()

        aggregate_row = (
            await self.db.execute(
                select(
                    func.count().label("missing_count"),
                    func.min(base_subq.c.transaction_date).label("earliest_transaction_date"),
                    func.max(base_subq.c.transaction_date).label("latest_transaction_date"),
                )
            )
        ).one()

        sample_rows = (
            await self.db.execute(
                select(base_subq)
                .order_by(
                    base_subq.c.transaction_date.asc(),
                    base_subq.c.transaction_id.asc(),
                )
                .limit(sample_limit)
            )
        ).all()

        return MissingHistoricalFxDependencySummary(
            missing_count=int(aggregate_row.missing_count or 0),
            earliest_transaction_date=aggregate_row.earliest_transaction_date,
            latest_transaction_date=aggregate_row.latest_transaction_date,
            sample_records=[
                MissingHistoricalFxDependencyRecord(
                    transaction_id=row.transaction_id,
                    security_id=row.security_id,
                    transaction_date=row.transaction_date,
                    trade_currency=row.trade_currency,
                    portfolio_currency=row.portfolio_currency,
                )
                for row in sample_rows
            ],
        )

    async def get_latest_financial_reconciliation_control_stage(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[PipelineStageState]:
        stmt = (
            select(PipelineStageState)
            .where(
                PipelineStageState.portfolio_id == portfolio_id,
                PipelineStageState.stage_name == "FINANCIAL_RECONCILIATION",
            )
        )
        if as_of is not None:
            stmt = stmt.where(PipelineStageState.updated_at <= as_of)
        stmt = stmt.order_by(
            PipelineStageState.business_date.desc(),
            PipelineStageState.epoch.desc(),
            PipelineStageState.id.desc(),
        ).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_reconciliation_run_for_portfolio_day(
        self,
        portfolio_id: str,
        business_date: date,
        epoch: int,
        as_of: Optional[datetime] = None,
    ) -> Optional[FinancialReconciliationRun]:
        stmt = (
            select(FinancialReconciliationRun)
            .where(
                FinancialReconciliationRun.portfolio_id == portfolio_id,
                FinancialReconciliationRun.business_date == business_date,
                FinancialReconciliationRun.epoch == epoch,
            )
        )
        if as_of is not None:
            stmt = stmt.where(
                FinancialReconciliationRun.started_at <= as_of,
                FinancialReconciliationRun.updated_at <= as_of,
            )
        stmt = stmt.order_by(
            self._reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
            FinancialReconciliationRun.started_at.desc(),
            FinancialReconciliationRun.id.desc(),
        ).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_state(
        self, portfolio_id: str, security_id: str, as_of: Optional[datetime] = None
    ) -> Optional[PositionState]:
        stmt = select(PositionState).where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.security_id == security_id,
        )
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_position_history_date(
        self, portfolio_id: str, security_id: str, epoch: int, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        stmt = select(func.max(PositionHistory.position_date)).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.epoch == epoch,
        )
        if as_of is not None:
            stmt = stmt.where(PositionHistory.created_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_daily_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        stmt = select(func.max(DailyPositionSnapshot.date)).where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.epoch == epoch,
        )
        if as_of is not None:
            stmt = stmt.where(DailyPositionSnapshot.created_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_valuation_job(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        as_of: Optional[datetime] = None,
    ) -> Optional[PortfolioValuationJob]:
        stmt = (
            select(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.epoch == epoch,
            )
        )
        if as_of is not None:
            stmt = stmt.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        stmt = stmt.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        ).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_lineage_keys_count(
        self,
        portfolio_id: str,
        reprocessing_status: Optional[str] = None,
        security_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(PositionState.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        if reprocessing_status:
            stmt = stmt.where(PositionState.status == reprocessing_status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_lineage_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        reprocessing_status: Optional[str] = None,
        security_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        latest_position_history_date = (
            select(func.max(PositionHistory.position_date))
            .where(
                PositionHistory.portfolio_id == PositionState.portfolio_id,
                PositionHistory.security_id == PositionState.security_id,
                PositionHistory.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_position_history_date = latest_position_history_date.where(
                PositionHistory.created_at <= as_of
            )
        latest_position_history_date = latest_position_history_date.correlate(
            PositionState
        ).scalar_subquery()
        latest_daily_snapshot_date = (
            select(func.max(DailyPositionSnapshot.date))
            .where(
                DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                DailyPositionSnapshot.security_id == PositionState.security_id,
                DailyPositionSnapshot.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_daily_snapshot_date = latest_daily_snapshot_date.where(
                DailyPositionSnapshot.created_at <= as_of
            )
        latest_daily_snapshot_date = latest_daily_snapshot_date.correlate(
            PositionState
        ).scalar_subquery()
        latest_valuation_job_date = (
            select(PortfolioValuationJob.valuation_date)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_valuation_job_date = latest_valuation_job_date.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        latest_valuation_job_date = latest_valuation_job_date.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        ).limit(1).correlate(PositionState).scalar_subquery()
        latest_valuation_job_id = (
            select(PortfolioValuationJob.id)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_valuation_job_id = latest_valuation_job_id.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        latest_valuation_job_id = latest_valuation_job_id.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        ).limit(1).correlate(PositionState).scalar_subquery()
        latest_valuation_job_status = (
            select(PortfolioValuationJob.status)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_valuation_job_status = latest_valuation_job_status.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        latest_valuation_job_status = latest_valuation_job_status.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        ).limit(1).correlate(PositionState).scalar_subquery()
        latest_valuation_job_correlation_id = (
            select(PortfolioValuationJob.correlation_id)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
        )
        if as_of is not None:
            latest_valuation_job_correlation_id = latest_valuation_job_correlation_id.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        latest_valuation_job_correlation_id = latest_valuation_job_correlation_id.order_by(
            PortfolioValuationJob.valuation_date.desc(),
            PortfolioValuationJob.id.desc(),
        ).limit(1).correlate(PositionState).scalar_subquery()
        has_artifact_gap = case(
            (latest_position_history_date.is_(None), False),
            (
                latest_daily_snapshot_date.is_(None),
                True,
            ),
            (
                latest_daily_snapshot_date < latest_position_history_date,
                True,
            ),
            (
                latest_valuation_job_date.is_(None),
                True,
            ),
            (
                latest_valuation_job_date < latest_position_history_date,
                True,
            ),
            (
                latest_valuation_job_status.in_(("FAILED", "PENDING", "PROCESSING")),
                True,
            ),
            else_=False,
        )
        lineage_priority = case(
            (PositionState.status == "REPROCESSING", 0),
            (
                and_(has_artifact_gap.is_(True), latest_valuation_job_status == "FAILED"),
                1,
            ),
            (has_artifact_gap.is_(True), 2),
            else_=9,
        )
        stmt = select(
            PositionState.security_id,
            PositionState.epoch,
            PositionState.watermark_date,
            PositionState.status.label("reprocessing_status"),
            latest_position_history_date.label("latest_position_history_date"),
            latest_daily_snapshot_date.label("latest_daily_snapshot_date"),
            latest_valuation_job_date.label("latest_valuation_job_date"),
            latest_valuation_job_id.label("latest_valuation_job_id"),
            latest_valuation_job_status.label("latest_valuation_job_status"),
            latest_valuation_job_correlation_id.label("latest_valuation_job_correlation_id"),
        ).where(PositionState.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        if reprocessing_status:
            stmt = stmt.where(PositionState.status == reprocessing_status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
        stmt = (
            stmt.order_by(
                lineage_priority.asc(),
                latest_position_history_date.desc().nullslast(),
                PositionState.security_id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).mappings().all())

    async def get_valuation_jobs_count(
        self,
        portfolio_id: str,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioValuationJob)
            .where(PortfolioValuationJob.portfolio_id == portfolio_id)
        )
        if job_id is None and correlation_id is None:
            stmt = stmt.where(self._is_actionable_valuation_job(as_of=as_of))
        if as_of is not None:
            stmt = stmt.where(PortfolioValuationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(PortfolioValuationJob.status == status)
        if business_date:
            stmt = stmt.where(PortfolioValuationJob.valuation_date == business_date)
        if security_id:
            stmt = stmt.where(PortfolioValuationJob.security_id == security_id)
        if job_id is not None:
            stmt = stmt.where(PortfolioValuationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioValuationJob.correlation_id == correlation_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_valuation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
    ) -> list[PortfolioValuationJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PortfolioValuationJob).where(
            PortfolioValuationJob.portfolio_id == portfolio_id
        )
        if job_id is None and correlation_id is None:
            stmt = stmt.where(self._is_actionable_valuation_job(as_of=as_of))
        if as_of is not None:
            stmt = stmt.where(PortfolioValuationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(PortfolioValuationJob.status == status)
        if business_date:
            stmt = stmt.where(PortfolioValuationJob.valuation_date == business_date)
        if security_id:
            stmt = stmt.where(PortfolioValuationJob.security_id == security_id)
        if job_id is not None:
            stmt = stmt.where(PortfolioValuationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioValuationJob.correlation_id == correlation_id)
        stmt = (
            stmt.order_by(
                self._support_job_priority(
                    PortfolioValuationJob.status,
                    PortfolioValuationJob.updated_at,
                    stale_threshold,
                ).asc(),
                PortfolioValuationJob.valuation_date.asc(),
                PortfolioValuationJob.updated_at.asc(),
                PortfolioValuationJob.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_aggregation_jobs_count(
        self,
        portfolio_id: str,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(PortfolioAggregationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(PortfolioAggregationJob.status == status)
        if business_date:
            stmt = stmt.where(PortfolioAggregationJob.aggregation_date == business_date)
        if job_id is not None:
            stmt = stmt.where(PortfolioAggregationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioAggregationJob.correlation_id == correlation_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_aggregation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
    ) -> list[PortfolioAggregationJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id
        )
        if as_of is not None:
            stmt = stmt.where(PortfolioAggregationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(PortfolioAggregationJob.status == status)
        if business_date:
            stmt = stmt.where(PortfolioAggregationJob.aggregation_date == business_date)
        if job_id is not None:
            stmt = stmt.where(PortfolioAggregationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioAggregationJob.correlation_id == correlation_id)
        stmt = (
            stmt.order_by(
                self._support_job_priority(
                    PortfolioAggregationJob.status,
                    PortfolioAggregationJob.updated_at,
                    stale_threshold,
                ).asc(),
                PortfolioAggregationJob.aggregation_date.asc(),
                PortfolioAggregationJob.updated_at.asc(),
                PortfolioAggregationJob.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_analytics_export_jobs_count(
        self,
        portfolio_id: str,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(AnalyticsExportJob)
            .where(AnalyticsExportJob.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(AnalyticsExportJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(AnalyticsExportJob.status == status)
        if job_id:
            stmt = stmt.where(AnalyticsExportJob.job_id == job_id)
        if request_fingerprint:
            stmt = stmt.where(AnalyticsExportJob.request_fingerprint == request_fingerprint)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_analytics_export_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
    ) -> list[AnalyticsExportJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(AnalyticsExportJob).where(AnalyticsExportJob.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(AnalyticsExportJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(AnalyticsExportJob.status == status)
        if job_id:
            stmt = stmt.where(AnalyticsExportJob.job_id == job_id)
        if request_fingerprint:
            stmt = stmt.where(AnalyticsExportJob.request_fingerprint == request_fingerprint)
        stmt = (
            stmt.order_by(
                self._analytics_export_job_priority(
                    AnalyticsExportJob.status,
                    AnalyticsExportJob.updated_at,
                    stale_threshold,
                ).asc(),
                AnalyticsExportJob.created_at.asc(),
                AnalyticsExportJob.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reconciliation_runs_count(
        self,
        portfolio_id: str,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        requested_by: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        reconciliation_type: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(FinancialReconciliationRun)
            .where(FinancialReconciliationRun.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationRun.updated_at <= as_of)
        if run_id:
            stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
        if correlation_id:
            stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
        if requested_by:
            stmt = stmt.where(FinancialReconciliationRun.requested_by == requested_by)
        if dedupe_key:
            stmt = stmt.where(FinancialReconciliationRun.dedupe_key == dedupe_key)
        if reconciliation_type:
            stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
        if status:
            stmt = stmt.where(FinancialReconciliationRun.status == status)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reconciliation_runs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        requested_by: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        reconciliation_type: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[FinancialReconciliationRun]:
        stmt = select(FinancialReconciliationRun).where(
            FinancialReconciliationRun.portfolio_id == portfolio_id
        )
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationRun.updated_at <= as_of)
        if run_id:
            stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
        if correlation_id:
            stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
        if requested_by:
            stmt = stmt.where(FinancialReconciliationRun.requested_by == requested_by)
        if dedupe_key:
            stmt = stmt.where(FinancialReconciliationRun.dedupe_key == dedupe_key)
        if reconciliation_type:
            stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
        if status:
            stmt = stmt.where(FinancialReconciliationRun.status == status)
        stmt = (
            stmt.order_by(
                self._reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
                FinancialReconciliationRun.started_at.desc(),
                FinancialReconciliationRun.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reconciliation_run(
        self, portfolio_id: str, run_id: str, as_of: Optional[datetime] = None
    ) -> Optional[FinancialReconciliationRun]:
        stmt = (
            select(FinancialReconciliationRun)
            .where(FinancialReconciliationRun.portfolio_id == portfolio_id)
            .where(FinancialReconciliationRun.run_id == run_id)
        )
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationRun.updated_at <= as_of)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_reconciliation_findings(
        self,
        run_id: str,
        limit: int,
        finding_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[FinancialReconciliationFinding]:
        severity_rank = case(
            (FinancialReconciliationFinding.severity == "ERROR", 0),
            (FinancialReconciliationFinding.severity == "WARNING", 1),
            (FinancialReconciliationFinding.severity == "INFO", 2),
            else_=9,
        )
        stmt = (
            select(FinancialReconciliationFinding)
            .where(FinancialReconciliationFinding.run_id == run_id)
        )
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationFinding.created_at <= as_of)
        if finding_id:
            stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
        if security_id:
            stmt = stmt.where(FinancialReconciliationFinding.security_id == security_id)
        if transaction_id:
            stmt = stmt.where(FinancialReconciliationFinding.transaction_id == transaction_id)
        stmt = (
            stmt.order_by(
                severity_rank.asc(),
                FinancialReconciliationFinding.finding_type.asc(),
                FinancialReconciliationFinding.created_at.desc(),
                FinancialReconciliationFinding.id.asc(),
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reconciliation_findings_count(
        self,
        run_id: str,
        finding_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(FinancialReconciliationFinding)
            .where(FinancialReconciliationFinding.run_id == run_id)
        )
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationFinding.created_at <= as_of)
        if finding_id:
            stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
        if security_id:
            stmt = stmt.where(FinancialReconciliationFinding.security_id == security_id)
        if transaction_id:
            stmt = stmt.where(FinancialReconciliationFinding.transaction_id == transaction_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reconciliation_finding_summary(
        self, run_id: str, as_of: Optional[datetime] = None
    ) -> ReconciliationFindingSummary:
        base_stmt = select(
            FinancialReconciliationFinding.severity.label("severity"),
            FinancialReconciliationFinding.created_at.label("created_at"),
            FinancialReconciliationFinding.id.label("id"),
            FinancialReconciliationFinding.finding_id.label("finding_id"),
            FinancialReconciliationFinding.finding_type.label("finding_type"),
            FinancialReconciliationFinding.security_id.label("security_id"),
            FinancialReconciliationFinding.transaction_id.label("transaction_id"),
        ).where(FinancialReconciliationFinding.run_id == run_id)
        if as_of is not None:
            base_stmt = base_stmt.where(FinancialReconciliationFinding.created_at <= as_of)
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count().label("total_findings"),
                func.count()
                .filter(base_subq.c.severity == "ERROR")
                .label("blocking_findings"),
            )
            .select_from(base_subq)
            .subquery()
        )
        top_blocking_subq = (
            select(
                base_subq.c.finding_id,
                base_subq.c.finding_type,
                base_subq.c.security_id,
                base_subq.c.transaction_id,
            )
            .where(base_subq.c.severity == "ERROR")
            .order_by(base_subq.c.created_at.desc(), base_subq.c.id.desc())
            .limit(1)
            .subquery()
        )
        row = (
            await self.db.execute(
                select(
                    aggregate_subq.c.total_findings,
                    aggregate_subq.c.blocking_findings,
                    top_blocking_subq.c.finding_id,
                    top_blocking_subq.c.finding_type,
                    top_blocking_subq.c.security_id,
                    top_blocking_subq.c.transaction_id,
                ).select_from(aggregate_subq).outerjoin(top_blocking_subq, true())
            )
        ).one()
        return ReconciliationFindingSummary(
            total_findings=int(row.total_findings or 0),
            blocking_findings=int(row.blocking_findings or 0),
            top_blocking_finding_id=row.finding_id,
            top_blocking_finding_type=row.finding_type,
            top_blocking_finding_security_id=row.security_id,
            top_blocking_finding_transaction_id=row.transaction_id,
        )

    async def get_portfolio_control_stages_count(
        self,
        portfolio_id: str,
        stage_id: Optional[int] = None,
        stage_name: Optional[str] = None,
        business_date: Optional[date] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PipelineStageState)
            .where(
                PipelineStageState.portfolio_id == portfolio_id,
                PipelineStageState.transaction_id.like("portfolio-stage:%"),
            )
        )
        if as_of is not None:
            stmt = stmt.where(PipelineStageState.updated_at <= as_of)
        if stage_id is not None:
            stmt = stmt.where(PipelineStageState.id == stage_id)
        if stage_name:
            stmt = stmt.where(PipelineStageState.stage_name == stage_name)
        if business_date:
            stmt = stmt.where(PipelineStageState.business_date == business_date)
        if status:
            stmt = stmt.where(PipelineStageState.status == status)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_portfolio_control_stages(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        stage_id: Optional[int] = None,
        stage_name: Optional[str] = None,
        business_date: Optional[date] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[PipelineStageState]:
        stmt = select(PipelineStageState).where(
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.transaction_id.like("portfolio-stage:%"),
        )
        if as_of is not None:
            stmt = stmt.where(PipelineStageState.updated_at <= as_of)
        if stage_id is not None:
            stmt = stmt.where(PipelineStageState.id == stage_id)
        if stage_name:
            stmt = stmt.where(PipelineStageState.stage_name == stage_name)
        if business_date:
            stmt = stmt.where(PipelineStageState.business_date == business_date)
        if status:
            stmt = stmt.where(PipelineStageState.status == status)
        stmt = (
            stmt.order_by(
                self._portfolio_control_stage_priority(PipelineStageState.status).asc(),
                PipelineStageState.business_date.desc(),
                PipelineStageState.epoch.desc(),
                PipelineStageState.updated_at.desc(),
                PipelineStageState.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reprocessing_keys_count(
        self,
        portfolio_id: str,
        status: Optional[str] = None,
        security_id: Optional[str] = None,
        watermark_date: Optional[date] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(PositionState.portfolio_id == portfolio_id)
        )
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        if status:
            stmt = stmt.where(PositionState.status == status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
        if watermark_date:
            stmt = stmt.where(PositionState.watermark_date == watermark_date)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reprocessing_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        security_id: Optional[str] = None,
        watermark_date: Optional[date] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
    ) -> list[PositionState]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PositionState).where(PositionState.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        if status:
            stmt = stmt.where(PositionState.status == status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
        if watermark_date:
            stmt = stmt.where(PositionState.watermark_date == watermark_date)
        stmt = (
            stmt.order_by(
                self._reprocessing_key_priority(
                    PositionState.status,
                    PositionState.updated_at,
                    stale_threshold,
                ).asc(),
                PositionState.updated_at.asc(),
                PositionState.security_id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reprocessing_jobs_count(
        self,
        portfolio_id: str,
        status: Optional[str] = None,
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        security_id_expr = ReprocessingJob.payload["security_id"].as_string()
        impacted_date_expr = cast(
            ReprocessingJob.payload["earliest_impacted_date"].as_string(),
            Date,
        )
        portfolio_scope_exists = self._reprocessing_job_portfolio_scope_exists(
            portfolio_id=portfolio_id,
            security_id_expr=security_id_expr,
            impacted_date_expr=impacted_date_expr,
        )
        stmt = (
            select(func.count())
            .select_from(ReprocessingJob)
            .where(
                ReprocessingJob.job_type == "RESET_WATERMARKS",
                portfolio_scope_exists,
            )
        )
        if as_of is not None:
            stmt = stmt.where(ReprocessingJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(ReprocessingJob.status == status)
        if security_id:
            stmt = stmt.where(security_id_expr == security_id)
        if job_id is not None:
            stmt = stmt.where(ReprocessingJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(ReprocessingJob.correlation_id == correlation_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reprocessing_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
    ):
        security_id_expr = ReprocessingJob.payload["security_id"].as_string()
        impacted_date_expr = ReprocessingJob.payload["earliest_impacted_date"].as_string()
        impacted_date_cast = cast(impacted_date_expr, Date)
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        portfolio_scope_exists = self._reprocessing_job_portfolio_scope_exists(
            portfolio_id=portfolio_id,
            security_id_expr=security_id_expr,
            impacted_date_expr=impacted_date_cast,
        )
        stmt = (
            select(
                ReprocessingJob.id,
                ReprocessingJob.job_type,
                impacted_date_expr.label("business_date"),
                ReprocessingJob.status,
                security_id_expr.label("security_id"),
                ReprocessingJob.attempt_count,
                ReprocessingJob.correlation_id,
                ReprocessingJob.created_at,
                ReprocessingJob.updated_at,
                ReprocessingJob.failure_reason,
            )
            .where(
                ReprocessingJob.job_type == "RESET_WATERMARKS",
                portfolio_scope_exists,
            )
        )
        if as_of is not None:
            stmt = stmt.where(ReprocessingJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(ReprocessingJob.status == status)
        if security_id:
            stmt = stmt.where(security_id_expr == security_id)
        if job_id is not None:
            stmt = stmt.where(ReprocessingJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(ReprocessingJob.correlation_id == correlation_id)
        stmt = (
            stmt.order_by(
                self._support_job_priority(
                    ReprocessingJob.status,
                    ReprocessingJob.updated_at,
                    stale_threshold,
                ).asc(),
                impacted_date_expr.asc(),
                ReprocessingJob.created_at.asc(),
                ReprocessingJob.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).all())
