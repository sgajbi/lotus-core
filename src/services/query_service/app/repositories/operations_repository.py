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
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    ReprocessingJob,
    Transaction,
)
from sqlalchemy import Date, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession


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


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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

    async def get_current_portfolio_epoch(self, portfolio_id: str) -> Optional[int]:
        stmt = select(func.max(PositionState.epoch)).where(
            PositionState.portfolio_id == portfolio_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_active_reprocessing_keys_count(self, portfolio_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.status == "REPROCESSING",
            )
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reprocessing_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        reference_now: datetime,
    ) -> ReprocessingHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(
            func.count()
            .filter(PositionState.status == "REPROCESSING")
            .label("active_keys"),
            func.count()
            .filter(
                PositionState.status == "REPROCESSING",
                PositionState.updated_at < stale_threshold,
            )
            .label("stale_reprocessing_keys"),
            func.min(PositionState.watermark_date)
            .filter(PositionState.status == "REPROCESSING")
            .label("oldest_reprocessing_watermark_date"),
        ).where(PositionState.portfolio_id == portfolio_id)
        row = (await self.db.execute(stmt)).one()
        oldest_key_stmt = (
            select(
                PositionState.security_id,
                PositionState.epoch,
                PositionState.updated_at,
            )
            .where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.status == "REPROCESSING",
            )
            .order_by(
                PositionState.watermark_date.asc(),
                PositionState.updated_at.asc(),
                PositionState.security_id.asc(),
            )
            .limit(1)
        )
        oldest_key_row = (await self.db.execute(oldest_key_stmt)).one_or_none()
        return ReprocessingHealthSummary(
            active_keys=int(row.active_keys or 0),
            stale_reprocessing_keys=int(row.stale_reprocessing_keys or 0),
            oldest_reprocessing_watermark_date=row.oldest_reprocessing_watermark_date,
            oldest_reprocessing_security_id=(
                oldest_key_row.security_id if oldest_key_row else None
            ),
            oldest_reprocessing_epoch=(oldest_key_row.epoch if oldest_key_row else None),
            oldest_reprocessing_updated_at=(
                oldest_key_row.updated_at if oldest_key_row else None
            ),
        )

    async def get_valuation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
    ) -> JobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        stmt = select(
            func.count()
            .filter(PortfolioValuationJob.status.in_(("PENDING", "PROCESSING")))
            .label("pending_jobs"),
            func.count()
            .filter(PortfolioValuationJob.status == "PROCESSING")
            .label("processing_jobs"),
            func.count()
            .filter(
                PortfolioValuationJob.status == "PROCESSING",
                PortfolioValuationJob.updated_at < stale_threshold,
            )
            .label("stale_processing_jobs"),
            func.count().filter(PortfolioValuationJob.status == "FAILED").label("failed_jobs"),
            func.count()
            .filter(
                PortfolioValuationJob.status == "FAILED",
                PortfolioValuationJob.updated_at >= failed_since,
            )
            .label("failed_jobs_last_hours"),
            func.min(PortfolioValuationJob.valuation_date)
            .filter(PortfolioValuationJob.status.in_(("PENDING", "PROCESSING")))
            .label("oldest_open_job_date"),
        ).where(PortfolioValuationJob.portfolio_id == portfolio_id)
        row = (await self.db.execute(stmt)).one()
        oldest_job_stmt = (
            select(
                PortfolioValuationJob.id,
                PortfolioValuationJob.security_id,
                PortfolioValuationJob.correlation_id,
            )
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.status.in_(("PENDING", "PROCESSING")),
            )
            .order_by(
                PortfolioValuationJob.valuation_date.asc(),
                PortfolioValuationJob.updated_at.asc(),
                PortfolioValuationJob.id.asc(),
            )
            .limit(1)
        )
        oldest_job_row = (await self.db.execute(oldest_job_stmt)).one_or_none()
        return JobHealthSummary(
            pending_jobs=int(row.pending_jobs or 0),
            processing_jobs=int(row.processing_jobs or 0),
            stale_processing_jobs=int(row.stale_processing_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_date=row.oldest_open_job_date,
            oldest_open_job_id=(oldest_job_row.id if oldest_job_row else None),
            oldest_open_job_correlation_id=(
                oldest_job_row.correlation_id if oldest_job_row else None
            ),
            oldest_open_security_id=(oldest_job_row.security_id if oldest_job_row else None),
        )

    async def get_aggregation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
    ) -> JobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        stmt = select(
            func.count()
            .filter(PortfolioAggregationJob.status.in_(("PENDING", "PROCESSING")))
            .label("pending_jobs"),
            func.count()
            .filter(PortfolioAggregationJob.status == "PROCESSING")
            .label("processing_jobs"),
            func.count()
            .filter(
                PortfolioAggregationJob.status == "PROCESSING",
                PortfolioAggregationJob.updated_at < stale_threshold,
            )
            .label("stale_processing_jobs"),
            func.count().filter(PortfolioAggregationJob.status == "FAILED").label("failed_jobs"),
            func.count()
            .filter(
                PortfolioAggregationJob.status == "FAILED",
                PortfolioAggregationJob.updated_at >= failed_since,
            )
            .label("failed_jobs_last_hours"),
            func.min(PortfolioAggregationJob.aggregation_date)
            .filter(PortfolioAggregationJob.status.in_(("PENDING", "PROCESSING")))
            .label("oldest_open_job_date"),
        ).where(PortfolioAggregationJob.portfolio_id == portfolio_id)
        row = (await self.db.execute(stmt)).one()
        oldest_job_stmt = (
            select(
                PortfolioAggregationJob.id,
                PortfolioAggregationJob.correlation_id,
            )
            .where(
                PortfolioAggregationJob.portfolio_id == portfolio_id,
                PortfolioAggregationJob.status.in_(("PENDING", "PROCESSING")),
            )
            .order_by(
                PortfolioAggregationJob.aggregation_date.asc(),
                PortfolioAggregationJob.updated_at.asc(),
                PortfolioAggregationJob.id.asc(),
            )
            .limit(1)
        )
        oldest_job_row = (await self.db.execute(oldest_job_stmt)).one_or_none()
        return JobHealthSummary(
            pending_jobs=int(row.pending_jobs or 0),
            processing_jobs=int(row.processing_jobs or 0),
            stale_processing_jobs=int(row.stale_processing_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_date=row.oldest_open_job_date,
            oldest_open_job_id=(oldest_job_row.id if oldest_job_row else None),
            oldest_open_job_correlation_id=(
                oldest_job_row.correlation_id if oldest_job_row else None
            ),
            oldest_open_security_id=None,
        )

    async def get_analytics_export_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
    ) -> ExportJobHealthSummary:
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        failed_since = reference_now - timedelta(hours=failed_window_hours)
        stmt = select(
            func.count().filter(AnalyticsExportJob.status == "accepted").label("accepted_jobs"),
            func.count().filter(AnalyticsExportJob.status == "running").label("running_jobs"),
            func.count()
            .filter(
                AnalyticsExportJob.status == "running",
                AnalyticsExportJob.updated_at < stale_threshold,
            )
            .label("stale_running_jobs"),
            func.count().filter(AnalyticsExportJob.status == "failed").label("failed_jobs"),
            func.count()
            .filter(
                AnalyticsExportJob.status == "failed",
                AnalyticsExportJob.updated_at >= failed_since,
            )
            .label("failed_jobs_last_hours"),
            func.min(AnalyticsExportJob.created_at)
            .filter(AnalyticsExportJob.status.in_(("accepted", "running")))
            .label("oldest_open_job_created_at"),
        ).where(AnalyticsExportJob.portfolio_id == portfolio_id)
        row = (await self.db.execute(stmt)).one()
        oldest_job_stmt = (
            select(
                AnalyticsExportJob.job_id,
                AnalyticsExportJob.request_fingerprint,
            )
            .where(
                AnalyticsExportJob.portfolio_id == portfolio_id,
                AnalyticsExportJob.status.in_(("accepted", "running")),
            )
            .order_by(
                AnalyticsExportJob.created_at.asc(),
                AnalyticsExportJob.updated_at.asc(),
                AnalyticsExportJob.job_id.asc(),
            )
            .limit(1)
        )
        oldest_job_row = (await self.db.execute(oldest_job_stmt)).one_or_none()
        return ExportJobHealthSummary(
            accepted_jobs=int(row.accepted_jobs or 0),
            running_jobs=int(row.running_jobs or 0),
            stale_running_jobs=int(row.stale_running_jobs or 0),
            failed_jobs=int(row.failed_jobs or 0),
            failed_jobs_last_hours=int(row.failed_jobs_last_hours or 0),
            oldest_open_job_created_at=row.oldest_open_job_created_at,
            oldest_open_job_id=(oldest_job_row.job_id if oldest_job_row else None),
            oldest_open_request_fingerprint=(
                oldest_job_row.request_fingerprint if oldest_job_row else None
            ),
        )

    async def get_latest_transaction_date(self, portfolio_id: str) -> Optional[date]:
        stmt = select(func.max(func.date(Transaction.transaction_date))).where(
            Transaction.portfolio_id == portfolio_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_transaction_date_as_of(
        self, portfolio_id: str, as_of_date: date
    ) -> Optional[date]:
        stmt = select(func.max(func.date(Transaction.transaction_date))).where(
            Transaction.portfolio_id == portfolio_id,
            func.date(Transaction.transaction_date) <= as_of_date,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_business_date(self) -> Optional[date]:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == DEFAULT_BUSINESS_CALENDAR_CODE
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch(self, portfolio_id: str) -> Optional[date]:
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
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch_as_of(
        self, portfolio_id: str, as_of_date: date
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
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_snapshot_history_mismatch_count(self, portfolio_id: str) -> int:
        latest_history = (
            select(
                PositionHistory.portfolio_id,
                PositionHistory.security_id,
                PositionHistory.epoch,
                func.max(PositionHistory.position_date).label("latest_history_date"),
            )
            .where(PositionHistory.portfolio_id == portfolio_id)
            .group_by(
                PositionHistory.portfolio_id, PositionHistory.security_id, PositionHistory.epoch
            )
            .subquery()
        )
        latest_snapshot = (
            select(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.security_id,
                DailyPositionSnapshot.epoch,
                func.max(DailyPositionSnapshot.date).label("latest_snapshot_date"),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
            .group_by(
                DailyPositionSnapshot.portfolio_id,
                DailyPositionSnapshot.security_id,
                DailyPositionSnapshot.epoch,
            )
            .subquery()
        )
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

    async def get_latest_financial_reconciliation_control_stage(
        self, portfolio_id: str
    ) -> Optional[PipelineStageState]:
        stmt = (
            select(PipelineStageState)
            .where(
                PipelineStageState.portfolio_id == portfolio_id,
                PipelineStageState.stage_name == "FINANCIAL_RECONCILIATION",
            )
            .order_by(
                PipelineStageState.business_date.desc(),
                PipelineStageState.epoch.desc(),
                PipelineStageState.id.desc(),
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_reconciliation_run_for_portfolio_day(
        self,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> Optional[FinancialReconciliationRun]:
        stmt = (
            select(FinancialReconciliationRun)
            .where(
                FinancialReconciliationRun.portfolio_id == portfolio_id,
                FinancialReconciliationRun.business_date == business_date,
                FinancialReconciliationRun.epoch == epoch,
            )
            .order_by(
                self._reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
                FinancialReconciliationRun.started_at.desc(),
                FinancialReconciliationRun.id.desc(),
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_state(
        self, portfolio_id: str, security_id: str
    ) -> Optional[PositionState]:
        stmt = select(PositionState).where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.security_id == security_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_position_history_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        stmt = select(func.max(PositionHistory.position_date)).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.epoch == epoch,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_daily_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        stmt = select(func.max(DailyPositionSnapshot.date)).where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.epoch == epoch,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_valuation_job(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[PortfolioValuationJob]:
        stmt = (
            select(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.epoch == epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_lineage_keys_count(
        self,
        portfolio_id: str,
        reprocessing_status: Optional[str] = None,
        security_id: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(PositionState.portfolio_id == portfolio_id)
        )
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
    ):
        latest_position_history_date = (
            select(func.max(PositionHistory.position_date))
            .where(
                PositionHistory.portfolio_id == PositionState.portfolio_id,
                PositionHistory.security_id == PositionState.security_id,
                PositionHistory.epoch == PositionState.epoch,
            )
            .correlate(PositionState)
            .scalar_subquery()
        )
        latest_daily_snapshot_date = (
            select(func.max(DailyPositionSnapshot.date))
            .where(
                DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                DailyPositionSnapshot.security_id == PositionState.security_id,
                DailyPositionSnapshot.epoch == PositionState.epoch,
            )
            .correlate(PositionState)
            .scalar_subquery()
        )
        latest_valuation_job_date = (
            select(PortfolioValuationJob.valuation_date)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
            .correlate(PositionState)
            .scalar_subquery()
        )
        latest_valuation_job_id = (
            select(PortfolioValuationJob.id)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
            .correlate(PositionState)
            .scalar_subquery()
        )
        latest_valuation_job_status = (
            select(PortfolioValuationJob.status)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
            .correlate(PositionState)
            .scalar_subquery()
        )
        latest_valuation_job_correlation_id = (
            select(PortfolioValuationJob.correlation_id)
            .where(
                PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
                PortfolioValuationJob.security_id == PositionState.security_id,
                PortfolioValuationJob.epoch == PositionState.epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
            .correlate(PositionState)
            .scalar_subquery()
        )
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
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioValuationJob)
            .where(PortfolioValuationJob.portfolio_id == portfolio_id)
        )
        if status:
            stmt = stmt.where(PortfolioValuationJob.status == status)
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
        security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
    ) -> list[PortfolioValuationJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PortfolioValuationJob).where(
            PortfolioValuationJob.portfolio_id == portfolio_id
        )
        if status:
            stmt = stmt.where(PortfolioValuationJob.status == status)
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
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.portfolio_id == portfolio_id)
        )
        if status:
            stmt = stmt.where(PortfolioAggregationJob.status == status)
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
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
    ) -> list[PortfolioAggregationJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id
        )
        if status:
            stmt = stmt.where(PortfolioAggregationJob.status == status)
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
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(AnalyticsExportJob)
            .where(AnalyticsExportJob.portfolio_id == portfolio_id)
        )
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
    ) -> list[AnalyticsExportJob]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(AnalyticsExportJob).where(AnalyticsExportJob.portfolio_id == portfolio_id)
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
        reconciliation_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(FinancialReconciliationRun)
            .where(FinancialReconciliationRun.portfolio_id == portfolio_id)
        )
        if run_id:
            stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
        if correlation_id:
            stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
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
        reconciliation_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[FinancialReconciliationRun]:
        stmt = select(FinancialReconciliationRun).where(
            FinancialReconciliationRun.portfolio_id == portfolio_id
        )
        if run_id:
            stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
        if correlation_id:
            stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
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
        self, portfolio_id: str, run_id: str
    ) -> Optional[FinancialReconciliationRun]:
        stmt = (
            select(FinancialReconciliationRun)
            .where(FinancialReconciliationRun.portfolio_id == portfolio_id)
            .where(FinancialReconciliationRun.run_id == run_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_reconciliation_findings(
        self, run_id: str, limit: int, finding_id: Optional[str] = None
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
        if finding_id:
            stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
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
        self, run_id: str, finding_id: Optional[str] = None
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(FinancialReconciliationFinding)
            .where(FinancialReconciliationFinding.run_id == run_id)
        )
        if finding_id:
            stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reconciliation_finding_summary(
        self, run_id: str
    ) -> ReconciliationFindingSummary:
        aggregate_stmt = (
            select(
                func.count().label("total_findings"),
                func.count()
                .filter(FinancialReconciliationFinding.severity == "ERROR")
                .label("blocking_findings"),
            )
            .select_from(FinancialReconciliationFinding)
            .where(FinancialReconciliationFinding.run_id == run_id)
        )
        row = (await self.db.execute(aggregate_stmt)).one()
        top_blocking_stmt = (
            select(
                FinancialReconciliationFinding.finding_id,
                FinancialReconciliationFinding.finding_type,
                FinancialReconciliationFinding.security_id,
                FinancialReconciliationFinding.transaction_id,
            )
            .where(
                FinancialReconciliationFinding.run_id == run_id,
                FinancialReconciliationFinding.severity == "ERROR",
            )
            .order_by(
                FinancialReconciliationFinding.created_at.desc(),
                FinancialReconciliationFinding.id.desc(),
            )
            .limit(1)
        )
        top_blocking_row = (await self.db.execute(top_blocking_stmt)).one_or_none()
        return ReconciliationFindingSummary(
            total_findings=int(row.total_findings or 0),
            blocking_findings=int(row.blocking_findings or 0),
            top_blocking_finding_id=(
                top_blocking_row.finding_id if top_blocking_row else None
            ),
            top_blocking_finding_type=(
                top_blocking_row.finding_type if top_blocking_row else None
            ),
            top_blocking_finding_security_id=(
                top_blocking_row.security_id if top_blocking_row else None
            ),
            top_blocking_finding_transaction_id=(
                top_blocking_row.transaction_id if top_blocking_row else None
            ),
        )

    async def get_portfolio_control_stages_count(
        self,
        portfolio_id: str,
        stage_id: Optional[int] = None,
        stage_name: Optional[str] = None,
        business_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PipelineStageState)
            .where(
                PipelineStageState.portfolio_id == portfolio_id,
                PipelineStageState.transaction_id.like("portfolio-stage:%"),
            )
        )
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
    ) -> list[PipelineStageState]:
        stmt = select(PipelineStageState).where(
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.transaction_id.like("portfolio-stage:%"),
        )
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
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(PositionState.portfolio_id == portfolio_id)
        )
        if status:
            stmt = stmt.where(PositionState.status == status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_reprocessing_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: Optional[str] = None,
        security_id: Optional[str] = None,
        stale_minutes: int = 15,
        reference_now: Optional[datetime] = None,
    ) -> list[PositionState]:
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = select(PositionState).where(PositionState.portfolio_id == portfolio_id)
        if status:
            stmt = stmt.where(PositionState.status == status)
        if security_id:
            stmt = stmt.where(PositionState.security_id == security_id)
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
