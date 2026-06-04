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
from sqlalchemy import Date, and_, case, cast, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .date_filters import start_of_next_day
from .identifier_normalization import normalize_security_id
from .operations_health_queries import (
    analytics_export_job_health_aggregate,
    analytics_export_job_health_result_select,
    analytics_export_job_health_summary_from_row,
    int_or_zero,
    oldest_open_analytics_export_job,
    oldest_open_support_job,
    seconds_or_none,
    support_job_health_aggregate,
    support_job_health_result_select,
    support_job_health_summary_from_row,
    support_job_health_thresholds,
)
from .operations_missing_fx_queries import (
    missing_historical_fx_aggregate_stmt,
    missing_historical_fx_base_stmt,
    missing_historical_fx_sample_stmt,
    missing_historical_fx_summary_from_rows,
)
from .operations_models import (
    ExportJobHealthSummary,
    JobHealthSummary,
    LoadRunProgressSummary,
    MissingHistoricalFxDependencySummary,
    ReconciliationFindingSummary,
    ReprocessingHealthSummary,
    ResetWatermarkReprocessingJobScope,
    SnapshotValuationCoverageSummary,
)


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _support_job_status_filter(status_column, status: str):
        return status_column == status.strip().upper()

    @staticmethod
    def _reprocessing_status_filter(status_column, status: str):
        return status_column == status.strip().upper()

    @staticmethod
    def _reconciliation_status_filter(status_column, status: str):
        return status_column == status.strip().upper()

    @staticmethod
    def _portfolio_control_status_filter(status_column, status: str):
        return status_column == status.strip().upper()

    @staticmethod
    def _security_id_expr(security_id_column):
        return func.trim(security_id_column)

    @staticmethod
    def _is_actionable_valuation_job(*, as_of: Optional[datetime] = None):
        superseding_job = aliased(PortfolioValuationJob)
        valuation_job_security_id = OperationsRepository._security_id_expr(
            PortfolioValuationJob.security_id
        )
        superseding_job_security_id = OperationsRepository._security_id_expr(
            superseding_job.security_id
        )
        superseded_pending_exists = select(superseding_job.id).where(
            superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
            superseding_job_security_id == valuation_job_security_id,
            superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
            superseding_job.epoch > PortfolioValuationJob.epoch,
        )
        if as_of is not None:
            superseded_pending_exists = superseded_pending_exists.where(
                superseding_job.updated_at <= as_of
            )

        return or_(
            PortfolioValuationJob.status != "PENDING",
            ~superseded_pending_exists.correlate(PortfolioValuationJob).exists(),
        )

    @staticmethod
    def _has_superseding_valuation_epoch(*, as_of: Optional[datetime] = None):
        superseding_job = aliased(PortfolioValuationJob)
        valuation_job_security_id = OperationsRepository._security_id_expr(
            PortfolioValuationJob.security_id
        )
        superseding_job_security_id = OperationsRepository._security_id_expr(
            superseding_job.security_id
        )
        superseding_exists = select(superseding_job.id).where(
            superseding_job.portfolio_id == PortfolioValuationJob.portfolio_id,
            superseding_job_security_id == valuation_job_security_id,
            superseding_job.valuation_date == PortfolioValuationJob.valuation_date,
            superseding_job.epoch > PortfolioValuationJob.epoch,
        )
        if as_of is not None:
            superseding_exists = superseding_exists.where(superseding_job.updated_at <= as_of)
        return superseding_exists.correlate(PortfolioValuationJob).exists()

    @staticmethod
    def _latest_valuation_job_lateral(position_state_security_id, as_of):
        valuation_job_security_id = OperationsRepository._security_id_expr(
            PortfolioValuationJob.security_id
        )
        latest_valuation_job = select(
            PortfolioValuationJob.valuation_date.label("latest_valuation_job_date"),
            PortfolioValuationJob.id.label("latest_valuation_job_id"),
            PortfolioValuationJob.status.label("latest_valuation_job_status"),
            PortfolioValuationJob.correlation_id.label("latest_valuation_job_correlation_id"),
        ).where(
            PortfolioValuationJob.portfolio_id == PositionState.portfolio_id,
            valuation_job_security_id == position_state_security_id,
            PortfolioValuationJob.epoch == PositionState.epoch,
        )
        if as_of is not None:
            latest_valuation_job = latest_valuation_job.where(
                PortfolioValuationJob.created_at <= as_of,
                PortfolioValuationJob.updated_at <= as_of,
            )
        return (
            latest_valuation_job.order_by(
                PortfolioValuationJob.valuation_date.desc(),
                PortfolioValuationJob.id.desc(),
            )
            .limit(1)
            .correlate(PositionState)
            .lateral()
        )

    @staticmethod
    def _reprocessing_job_portfolio_scope_exists(
        portfolio_id: str,
        security_id_expr,
        impacted_date_expr,
    ):
        position_state_security_id = OperationsRepository._security_id_expr(
            PositionState.security_id
        )
        position_history_security_id = OperationsRepository._security_id_expr(
            PositionHistory.security_id
        )
        latest_history = select(
            PositionHistory.quantity.label("quantity"),
            func.row_number()
            .over(
                partition_by=PositionHistory.portfolio_id,
                order_by=[PositionHistory.position_date.desc(), PositionHistory.id.desc()],
            )
            .label("rn"),
        )
        latest_history = OperationsRepository._apply_current_position_history_scope(
            latest_history,
            portfolio_id=portfolio_id,
            position_history_security_id=position_history_security_id,
            position_state_security_id=position_state_security_id,
            normalized_security_id=security_id_expr,
            history_date_on_or_before=impacted_date_expr,
        )
        latest_history = latest_history.correlate(ReprocessingJob).subquery()

        return (
            select(1)
            .select_from(latest_history)
            .where(latest_history.c.rn == 1, latest_history.c.quantity > 0)
            .exists()
        )

    @staticmethod
    def _reset_watermark_reprocessing_job_scope(
        portfolio_id: str,
    ) -> ResetWatermarkReprocessingJobScope:
        security_id_expr = func.trim(ReprocessingJob.payload["security_id"].as_string())
        impacted_date_expr = ReprocessingJob.payload["earliest_impacted_date"].as_string()
        impacted_date_cast = cast(impacted_date_expr, Date)
        portfolio_scope_exists = OperationsRepository._reprocessing_job_portfolio_scope_exists(
            portfolio_id=portfolio_id,
            security_id_expr=security_id_expr,
            impacted_date_expr=impacted_date_cast,
        )
        return ResetWatermarkReprocessingJobScope(
            security_id_expr=security_id_expr,
            impacted_date_expr=impacted_date_expr,
            portfolio_scope_exists=portfolio_scope_exists,
        )

    @staticmethod
    def _support_job_priority(status_column, updated_at_column, stale_threshold: datetime):
        governed_status = status_column
        return case(
            (governed_status == "FAILED", 0),
            (
                and_(governed_status == "PROCESSING", updated_at_column < stale_threshold),
                1,
            ),
            (governed_status == "PROCESSING", 2),
            (governed_status == "PENDING", 3),
            else_=9,
        )

    def _apply_valuation_actionable_scope(
        self,
        stmt,
        *,
        job_id: Optional[int],
        correlation_id: Optional[str],
        as_of: Optional[datetime],
    ):
        if job_id is None and correlation_id is None:
            return stmt.where(self._is_actionable_valuation_job(as_of=as_of))
        return stmt

    @staticmethod
    def _apply_valuation_identity_scope(
        stmt,
        *,
        job_id: Optional[int],
        correlation_id: Optional[str],
    ):
        if job_id is not None:
            stmt = stmt.where(PortfolioValuationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioValuationJob.correlation_id == correlation_id)
        return stmt

    def _apply_valuation_attribute_scope(
        self,
        stmt,
        *,
        business_date: Optional[date],
        normalized_security_id: Optional[str],
    ):
        if business_date:
            stmt = stmt.where(PortfolioValuationJob.valuation_date == business_date)
        if normalized_security_id:
            valuation_job_security_id = self._security_id_expr(PortfolioValuationJob.security_id)
            stmt = stmt.where(valuation_job_security_id == normalized_security_id)
        return stmt

    @staticmethod
    def _apply_aggregation_identity_scope(
        stmt,
        *,
        job_id: Optional[int],
        correlation_id: Optional[str],
    ):
        if job_id is not None:
            stmt = stmt.where(PortfolioAggregationJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(PortfolioAggregationJob.correlation_id == correlation_id)
        return stmt

    @staticmethod
    def _apply_aggregation_attribute_scope(
        stmt,
        *,
        business_date: Optional[date],
    ):
        if business_date:
            stmt = stmt.where(PortfolioAggregationJob.aggregation_date == business_date)
        return stmt

    def _apply_valuation_job_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        normalized_security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(PortfolioValuationJob.portfolio_id == portfolio_id)
        stmt = self._apply_valuation_actionable_scope(
            stmt,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
        if as_of is not None:
            stmt = stmt.where(PortfolioValuationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(self._support_job_status_filter(PortfolioValuationJob.status, status))
        stmt = self._apply_valuation_attribute_scope(
            stmt,
            business_date=business_date,
            normalized_security_id=normalized_security_id,
        )
        stmt = self._apply_valuation_identity_scope(
            stmt,
            job_id=job_id,
            correlation_id=correlation_id,
        )
        return stmt

    def _apply_aggregation_job_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        status: Optional[str] = None,
        business_date: Optional[date] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(PortfolioAggregationJob.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(PortfolioAggregationJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(
                self._support_job_status_filter(PortfolioAggregationJob.status, status)
            )
        stmt = self._apply_aggregation_attribute_scope(stmt, business_date=business_date)
        stmt = self._apply_aggregation_identity_scope(
            stmt,
            job_id=job_id,
            correlation_id=correlation_id,
        )
        return stmt

    @staticmethod
    def _analytics_export_status_filter(status_column, status: str):
        return status_column == status.strip().lower()

    @staticmethod
    def _analytics_export_job_priority(status_column, updated_at_column, stale_threshold: datetime):
        governed_status = status_column
        return case(
            (governed_status == "failed", 0),
            (
                and_(governed_status == "running", updated_at_column < stale_threshold),
                1,
            ),
            (governed_status == "running", 2),
            (governed_status == "accepted", 3),
            else_=9,
        )

    def _apply_analytics_export_job_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(AnalyticsExportJob.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(AnalyticsExportJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(
                self._analytics_export_status_filter(AnalyticsExportJob.status, status)
            )
        if job_id:
            stmt = stmt.where(AnalyticsExportJob.job_id == job_id)
        if request_fingerprint:
            stmt = stmt.where(AnalyticsExportJob.request_fingerprint == request_fingerprint)
        return stmt

    @staticmethod
    def _reconciliation_run_priority(status_column):
        governed_status = status_column
        return case(
            (governed_status.in_(("FAILED", "REQUIRES_REPLAY")), 0),
            (governed_status == "RUNNING", 1),
            else_=9,
        )

    @staticmethod
    def _apply_reconciliation_run_time_scope(
        stmt,
        *,
        as_of: Optional[datetime],
        include_started_as_of: bool,
    ):
        if as_of is None:
            return stmt
        stmt = stmt.where(FinancialReconciliationRun.updated_at <= as_of)
        if include_started_as_of:
            stmt = stmt.where(FinancialReconciliationRun.started_at <= as_of)
        return stmt

    @staticmethod
    def _apply_reconciliation_run_identity_scope(
        stmt,
        *,
        run_id: Optional[str],
        correlation_id: Optional[str],
        requested_by: Optional[str],
        dedupe_key: Optional[str],
    ):
        if run_id:
            stmt = stmt.where(FinancialReconciliationRun.run_id == run_id)
        if correlation_id:
            stmt = stmt.where(FinancialReconciliationRun.correlation_id == correlation_id)
        if requested_by:
            stmt = stmt.where(FinancialReconciliationRun.requested_by == requested_by)
        if dedupe_key:
            stmt = stmt.where(FinancialReconciliationRun.dedupe_key == dedupe_key)
        return stmt

    @staticmethod
    def _apply_reconciliation_run_attribute_scope(
        stmt,
        *,
        reconciliation_type: Optional[str],
        business_date: Optional[date],
        epoch: Optional[int],
    ):
        if reconciliation_type:
            stmt = stmt.where(FinancialReconciliationRun.reconciliation_type == reconciliation_type)
        if business_date is not None:
            stmt = stmt.where(FinancialReconciliationRun.business_date == business_date)
        if epoch is not None:
            stmt = stmt.where(FinancialReconciliationRun.epoch == epoch)
        return stmt

    def _apply_reconciliation_run_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        requested_by: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        reconciliation_type: Optional[str] = None,
        business_date: Optional[date] = None,
        epoch: Optional[int] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        include_started_as_of: bool = False,
    ):
        stmt = stmt.where(FinancialReconciliationRun.portfolio_id == portfolio_id)
        stmt = self._apply_reconciliation_run_time_scope(
            stmt,
            as_of=as_of,
            include_started_as_of=include_started_as_of,
        )
        stmt = self._apply_reconciliation_run_identity_scope(
            stmt,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
        )
        stmt = self._apply_reconciliation_run_attribute_scope(
            stmt,
            reconciliation_type=reconciliation_type,
            business_date=business_date,
            epoch=epoch,
        )
        if status:
            stmt = stmt.where(
                self._reconciliation_status_filter(FinancialReconciliationRun.status, status)
            )
        return stmt

    def _apply_reconciliation_finding_scope(
        self,
        stmt,
        *,
        run_id: str,
        finding_id: Optional[str] = None,
        normalized_security_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(FinancialReconciliationFinding.run_id == run_id)
        if as_of is not None:
            stmt = stmt.where(FinancialReconciliationFinding.created_at <= as_of)
        if finding_id:
            stmt = stmt.where(FinancialReconciliationFinding.finding_id == finding_id)
        if normalized_security_id:
            finding_security_id = self._security_id_expr(FinancialReconciliationFinding.security_id)
            stmt = stmt.where(finding_security_id == normalized_security_id)
        if transaction_id:
            stmt = stmt.where(FinancialReconciliationFinding.transaction_id == transaction_id)
        return stmt

    @staticmethod
    def _portfolio_control_stage_priority(status_column):
        governed_status = status_column
        return case(
            (governed_status.in_(("FAILED", "REQUIRES_REPLAY")), 0),
            else_=9,
        )

    @staticmethod
    def _apply_portfolio_control_stage_identity_scope(
        stmt,
        *,
        stage_id: Optional[int],
        stage_name: Optional[str],
    ):
        if stage_id is not None:
            stmt = stmt.where(PipelineStageState.id == stage_id)
        if stage_name:
            stmt = stmt.where(PipelineStageState.stage_name == stage_name)
        return stmt

    @staticmethod
    def _apply_portfolio_control_stage_attribute_scope(
        stmt,
        *,
        business_date: Optional[date],
    ):
        if business_date:
            stmt = stmt.where(PipelineStageState.business_date == business_date)
        return stmt

    def _apply_portfolio_control_stage_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        stage_id: Optional[int] = None,
        stage_name: Optional[str] = None,
        business_date: Optional[date] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.transaction_id.like("portfolio-stage:%"),
        )
        if as_of is not None:
            stmt = stmt.where(PipelineStageState.updated_at <= as_of)
        stmt = self._apply_portfolio_control_stage_identity_scope(
            stmt,
            stage_id=stage_id,
            stage_name=stage_name,
        )
        stmt = self._apply_portfolio_control_stage_attribute_scope(
            stmt,
            business_date=business_date,
        )
        if status:
            stmt = stmt.where(
                self._portfolio_control_status_filter(PipelineStageState.status, status)
            )
        return stmt

    @staticmethod
    def _reprocessing_key_priority(status_column, updated_at_column, stale_threshold: datetime):
        governed_status = status_column
        return case(
            (
                and_(governed_status == "REPROCESSING", updated_at_column < stale_threshold),
                0,
            ),
            (governed_status == "REPROCESSING", 1),
            else_=9,
        )

    @staticmethod
    def _apply_reprocessing_job_identity_scope(
        stmt,
        *,
        job_id: Optional[int],
        correlation_id: Optional[str],
    ):
        if job_id is not None:
            stmt = stmt.where(ReprocessingJob.id == job_id)
        if correlation_id:
            stmt = stmt.where(ReprocessingJob.correlation_id == correlation_id)
        return stmt

    @staticmethod
    def _apply_reprocessing_job_security_scope(
        stmt,
        *,
        reset_scope: ResetWatermarkReprocessingJobScope,
        normalized_security_id: Optional[str],
    ):
        if normalized_security_id:
            stmt = stmt.where(reset_scope.security_id_expr == normalized_security_id)
        return stmt

    def _apply_reprocessing_key_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        status: Optional[str] = None,
        normalized_security_id: Optional[str] = None,
        watermark_date: Optional[date] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(PositionState.portfolio_id == portfolio_id)
        if as_of is not None:
            stmt = stmt.where(PositionState.updated_at <= as_of)
        if status:
            stmt = stmt.where(self._reprocessing_status_filter(PositionState.status, status))
        if normalized_security_id:
            state_security_id = self._security_id_expr(PositionState.security_id)
            stmt = stmt.where(state_security_id == normalized_security_id)
        if watermark_date:
            stmt = stmt.where(PositionState.watermark_date == watermark_date)
        return stmt

    def _apply_reprocessing_job_scope(
        self,
        stmt,
        *,
        reset_scope: ResetWatermarkReprocessingJobScope,
        status: Optional[str] = None,
        normalized_security_id: Optional[str] = None,
        job_id: Optional[int] = None,
        correlation_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(
            ReprocessingJob.job_type == "RESET_WATERMARKS",
            reset_scope.portfolio_scope_exists,
        )
        if as_of is not None:
            stmt = stmt.where(ReprocessingJob.updated_at <= as_of)
        if status:
            stmt = stmt.where(self._support_job_status_filter(ReprocessingJob.status, status))
        stmt = self._apply_reprocessing_job_security_scope(
            stmt,
            reset_scope=reset_scope,
            normalized_security_id=normalized_security_id,
        )
        stmt = self._apply_reprocessing_job_identity_scope(
            stmt,
            job_id=job_id,
            correlation_id=correlation_id,
        )
        return stmt

    async def _get_support_job_health_summary(
        self,
        base_stmt,
        *,
        open_date_column_name: str,
        stale_threshold: datetime,
        failed_since: datetime,
        include_security: bool = False,
    ) -> JobHealthSummary:
        base_subq = base_stmt.subquery()
        open_date_column = getattr(base_subq.c, open_date_column_name)
        extra_columns = (base_subq.c.security_id,) if include_security else ()
        aggregate_subq = support_job_health_aggregate(
            base_subq,
            open_date_column,
            stale_threshold,
            failed_since,
        )
        oldest_job_subq = oldest_open_support_job(
            base_subq,
            open_date_column,
            *extra_columns,
        )
        row = (
            await self.db.execute(
                support_job_health_result_select(
                    aggregate_subq,
                    oldest_job_subq,
                    include_security=include_security,
                )
            )
        ).one()
        return support_job_health_summary_from_row(
            row,
            include_security=include_security,
        )

    async def _get_analytics_export_job_health_summary(
        self,
        base_stmt,
        *,
        stale_threshold: datetime,
        failed_since: datetime,
    ) -> ExportJobHealthSummary:
        base_subq = base_stmt.subquery()
        aggregate_subq = analytics_export_job_health_aggregate(
            base_subq,
            stale_threshold=stale_threshold,
            failed_since=failed_since,
        )
        oldest_job_subq = oldest_open_analytics_export_job(base_subq)
        row = (
            await self.db.execute(
                analytics_export_job_health_result_select(
                    aggregate_subq,
                    oldest_job_subq,
                )
            )
        ).one()
        return analytics_export_job_health_summary_from_row(row)

    @staticmethod
    def _lineage_latest_date_subquery(
        model,
        date_column,
        security_id_expr,
        position_state_security_id,
        *,
        as_of_column=None,
        as_of: Optional[datetime] = None,
    ):
        stmt = select(func.max(date_column)).where(
            model.portfolio_id == PositionState.portfolio_id,
            security_id_expr == position_state_security_id,
            model.epoch == PositionState.epoch,
        )
        if as_of is not None and as_of_column is not None:
            stmt = stmt.where(as_of_column <= as_of)
        return stmt.correlate(PositionState).scalar_subquery()

    @staticmethod
    def _lineage_artifact_gap_case(
        *,
        latest_position_history_date,
        latest_daily_snapshot_date,
        latest_valuation_job_date,
        latest_valuation_job_status,
    ):
        return case(
            (latest_position_history_date.is_(None), False),
            (latest_daily_snapshot_date.is_(None), True),
            (latest_daily_snapshot_date < latest_position_history_date, True),
            (latest_valuation_job_date.is_(None), True),
            (latest_valuation_job_date < latest_position_history_date, True),
            (latest_valuation_job_status.in_(("FAILED", "PENDING", "PROCESSING")), True),
            else_=False,
        )

    @staticmethod
    def _lineage_priority_case(*, has_artifact_gap, latest_valuation_job_status):
        return case(
            (PositionState.status == "REPROCESSING", 0),
            (
                and_(has_artifact_gap.is_(True), latest_valuation_job_status == "FAILED"),
                1,
            ),
            (has_artifact_gap.is_(True), 2),
            else_=9,
        )

    @staticmethod
    def _lineage_keys_select(
        *,
        position_state_security_id,
        latest_position_history_date,
        latest_daily_snapshot_date,
        latest_valuation_job,
    ):
        return (
            select(
                position_state_security_id.label("security_id"),
                PositionState.epoch,
                PositionState.watermark_date,
                PositionState.status.label("reprocessing_status"),
                latest_position_history_date.label("latest_position_history_date"),
                latest_daily_snapshot_date.label("latest_daily_snapshot_date"),
                latest_valuation_job.c.latest_valuation_job_date.label("latest_valuation_job_date"),
                latest_valuation_job.c.latest_valuation_job_id.label("latest_valuation_job_id"),
                latest_valuation_job.c.latest_valuation_job_status.label(
                    "latest_valuation_job_status"
                ),
                latest_valuation_job.c.latest_valuation_job_correlation_id.label(
                    "latest_valuation_job_correlation_id"
                ),
            )
            .select_from(PositionState)
            .outerjoin(latest_valuation_job, true())
        )

    @staticmethod
    def _apply_load_run_artifact_scope(
        stmt,
        artifact_model,
        *,
        portfolio_pattern: str,
        business_date: Optional[date] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(artifact_model.portfolio_id.like(portfolio_pattern))
        if business_date is not None:
            stmt = stmt.where(artifact_model.date == business_date)
        if as_of is not None:
            stmt = stmt.where(artifact_model.created_at <= as_of)
        return stmt

    @staticmethod
    def _apply_load_run_job_scope(
        stmt,
        job_model,
        *,
        portfolio_pattern: str,
        as_of: Optional[datetime] = None,
    ):
        stmt = stmt.where(job_model.portfolio_id.like(portfolio_pattern))
        if as_of is not None:
            stmt = stmt.where(job_model.updated_at <= as_of)
        return stmt

    @staticmethod
    def _apply_portfolio_security_epoch_scope(
        stmt,
        evidence_model,
        security_id_expr,
        *,
        portfolio_id: str,
        normalized_security_id: str,
        epoch: int,
        as_of: Optional[datetime] = None,
        as_of_columns=(),
    ):
        stmt = stmt.where(
            evidence_model.portfolio_id == portfolio_id,
            security_id_expr == normalized_security_id,
            evidence_model.epoch == epoch,
        )
        if as_of is not None:
            for as_of_column in as_of_columns:
                stmt = stmt.where(as_of_column <= as_of)
        return stmt

    @staticmethod
    def _position_history_security_expressions(
        *,
        position_history_security_id=None,
        position_state_security_id=None,
    ):
        return (
            position_history_security_id
            if position_history_security_id is not None
            else OperationsRepository._security_id_expr(PositionHistory.security_id),
            position_state_security_id
            if position_state_security_id is not None
            else OperationsRepository._security_id_expr(PositionState.security_id),
        )

    @staticmethod
    def _apply_position_history_security_scope(
        stmt,
        *,
        position_history_security_id,
        position_state_security_id,
        normalized_security_id=None,
    ):
        if normalized_security_id is None:
            return stmt
        return stmt.where(
            position_history_security_id == normalized_security_id,
            position_state_security_id == normalized_security_id,
        )

    @staticmethod
    def _apply_position_history_time_scope(
        stmt,
        *,
        history_date_on_or_before=None,
        history_as_of: Optional[datetime] = None,
    ):
        if history_date_on_or_before is not None:
            stmt = stmt.where(PositionHistory.position_date <= history_date_on_or_before)
        if history_as_of is not None:
            stmt = stmt.where(
                PositionHistory.created_at <= history_as_of,
                PositionState.updated_at <= history_as_of,
            )
        return stmt

    @staticmethod
    def _apply_current_position_history_scope(
        stmt,
        *,
        portfolio_id: str,
        position_history_security_id=None,
        position_state_security_id=None,
        normalized_security_id=None,
        history_date_on_or_before=None,
        history_as_of: Optional[datetime] = None,
    ):
        (
            position_history_security_id,
            position_state_security_id,
        ) = OperationsRepository._position_history_security_expressions(
            position_history_security_id=position_history_security_id,
            position_state_security_id=position_state_security_id,
        )
        stmt = stmt.join(
            PositionState,
            and_(
                PositionHistory.portfolio_id == PositionState.portfolio_id,
                position_history_security_id == position_state_security_id,
                PositionHistory.epoch == PositionState.epoch,
            ),
        ).where(PositionHistory.portfolio_id == portfolio_id)
        stmt = OperationsRepository._apply_position_history_security_scope(
            stmt,
            position_history_security_id=position_history_security_id,
            position_state_security_id=position_state_security_id,
            normalized_security_id=normalized_security_id,
        )
        return OperationsRepository._apply_position_history_time_scope(
            stmt,
            history_date_on_or_before=history_date_on_or_before,
            history_as_of=history_as_of,
        )

    def _current_epoch_snapshot_date_stmt(
        self,
        *,
        portfolio_id: str,
        as_of_date: Optional[date] = None,
        snapshot_as_of: Optional[datetime] = None,
    ):
        return self._apply_current_epoch_snapshot_scope(
            select(func.max(DailyPositionSnapshot.date)),
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            snapshot_as_of=snapshot_as_of,
        )

    def _apply_current_epoch_snapshot_scope(
        self,
        stmt,
        *,
        portfolio_id: str,
        snapshot_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        snapshot_as_of: Optional[datetime] = None,
    ):
        snapshot_security_id = self._security_id_expr(DailyPositionSnapshot.security_id)
        state_security_id = self._security_id_expr(PositionState.security_id)
        stmt = stmt.join(
            PositionState,
            and_(
                DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                snapshot_security_id == state_security_id,
                DailyPositionSnapshot.epoch == PositionState.epoch,
            ),
        ).where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        if snapshot_date is not None:
            stmt = stmt.where(DailyPositionSnapshot.date == snapshot_date)
        if as_of_date is not None:
            stmt = stmt.where(DailyPositionSnapshot.date <= as_of_date)
        if snapshot_as_of is not None:
            stmt = stmt.where(
                DailyPositionSnapshot.created_at <= snapshot_as_of,
                PositionState.updated_at <= snapshot_as_of,
            )
        return stmt

    @staticmethod
    def _latest_transaction_date_stmt(
        *,
        portfolio_id: str,
        as_of_date: Optional[date] = None,
        snapshot_as_of: Optional[datetime] = None,
    ):
        stmt = select(func.max(Transaction.transaction_date)).where(
            Transaction.portfolio_id == portfolio_id
        )
        if as_of_date is not None:
            stmt = stmt.where(Transaction.transaction_date < start_of_next_day(as_of_date))
        if snapshot_as_of is not None:
            stmt = stmt.where(Transaction.created_at <= snapshot_as_of)
        return stmt

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        stmt = select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    def _load_run_progress_scalar_statements(
        self,
        *,
        portfolio_pattern: str,
        transaction_pattern: str,
        business_date: date,
        as_of: Optional[datetime],
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
        snapshot_portfolios_stmt = self._apply_load_run_artifact_scope(
            select(func.count(func.distinct(DailyPositionSnapshot.portfolio_id))),
            DailyPositionSnapshot,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        snapshot_rows_stmt = self._apply_load_run_artifact_scope(
            select(func.count()).select_from(DailyPositionSnapshot),
            DailyPositionSnapshot,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        position_timeseries_portfolios_stmt = self._apply_load_run_artifact_scope(
            select(func.count(func.distinct(PositionTimeseries.portfolio_id))),
            PositionTimeseries,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        position_timeseries_rows_stmt = self._apply_load_run_artifact_scope(
            select(func.count()).select_from(PositionTimeseries),
            PositionTimeseries,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        timeseries_portfolios_stmt = self._apply_load_run_artifact_scope(
            select(func.count(func.distinct(PortfolioTimeseries.portfolio_id))),
            PortfolioTimeseries,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        timeseries_rows_stmt = self._apply_load_run_artifact_scope(
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
        ) = self._load_run_progress_valuation_handoff_statements(
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        )
        latest_snapshot_stmt = self._apply_load_run_artifact_scope(
            select(func.max(DailyPositionSnapshot.date)),
            DailyPositionSnapshot,
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        )
        latest_snapshot_materialized_stmt = self._apply_load_run_artifact_scope(
            select(func.max(DailyPositionSnapshot.created_at)),
            DailyPositionSnapshot,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        latest_position_timeseries_materialized_stmt = self._apply_load_run_artifact_scope(
            select(func.max(PositionTimeseries.created_at)),
            PositionTimeseries,
            portfolio_pattern=portfolio_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        latest_timeseries_stmt = self._apply_load_run_artifact_scope(
            select(func.max(PortfolioTimeseries.date)),
            PortfolioTimeseries,
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        )
        latest_portfolio_timeseries_materialized_stmt = self._apply_load_run_artifact_scope(
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

    def _load_run_progress_execute_statements(
        self,
        *,
        portfolio_pattern: str,
        as_of: Optional[datetime],
    ):
        valuation_base = select(
            PortfolioValuationJob.status.label("status"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.updated_at.label("updated_at"),
        )
        valuation_base = self._apply_load_run_job_scope(
            valuation_base,
            PortfolioValuationJob,
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        ).where(self._is_actionable_valuation_job(as_of=as_of))
        valuation_subq = valuation_base.subquery()

        aggregation_base = select(
            PortfolioAggregationJob.status.label("status"),
            PortfolioAggregationJob.aggregation_date.label("aggregation_date"),
            PortfolioAggregationJob.updated_at.label("updated_at"),
        )
        aggregation_base = self._apply_load_run_job_scope(
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
        ) = self._load_run_progress_valuation_handoff_statements(
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        )
        return (
            valuation_summary_stmt,
            aggregation_summary_stmt,
            valuation_handoff_latency_stmt,
            valuation_without_position_timeseries_stmt,
        )

    def _load_run_progress_valuation_handoff_statements(
        self,
        *,
        portfolio_pattern: str,
        as_of: Optional[datetime],
    ):
        valuation_handoff_base = select(
            PortfolioValuationJob.portfolio_id.label("portfolio_id"),
            self._security_id_expr(PortfolioValuationJob.security_id).label("security_id"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.epoch.label("epoch"),
            PortfolioValuationJob.updated_at.label("valuation_completed_at_utc"),
        )
        valuation_handoff_base = self._apply_load_run_job_scope(
            valuation_handoff_base,
            PortfolioValuationJob,
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        ).where(
            PortfolioValuationJob.status == "COMPLETE",
            ~self._has_superseding_valuation_epoch(as_of=as_of),
        )
        valuation_handoff_subq = valuation_handoff_base.subquery()
        valuation_to_position_join = and_(
            PositionTimeseries.portfolio_id == valuation_handoff_subq.c.portfolio_id,
            self._security_id_expr(PositionTimeseries.security_id)
            == valuation_handoff_subq.c.security_id,
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

    @staticmethod
    def _load_run_progress_summary_from_rows(
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

    async def get_load_run_progress(
        self,
        run_id: str,
        business_date: date,
        as_of: Optional[datetime] = None,
    ) -> LoadRunProgressSummary:
        portfolio_pattern = f"LOAD_{run_id}_PF_%"
        transaction_pattern = f"LOAD_{run_id}_TX_%"
        scalar_statements = self._load_run_progress_scalar_statements(
            portfolio_pattern=portfolio_pattern,
            transaction_pattern=transaction_pattern,
            business_date=business_date,
            as_of=as_of,
        )
        execute_statements = self._load_run_progress_execute_statements(
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
        )

        scalar_values = [await self.db.scalar(stmt) for stmt in scalar_statements]
        execute_rows = [(await self.db.execute(stmt)).one() for stmt in execute_statements]
        return self._load_run_progress_summary_from_rows(
            scalar_values=scalar_values,
            valuation_summary=execute_rows[0],
            aggregation_summary=execute_rows[1],
            valuation_handoff_latency=execute_rows[2],
            valuation_without_position_timeseries=execute_rows[3],
        )

    async def get_current_portfolio_epoch(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[int]:
        stmt = self._apply_reprocessing_key_scope(
            select(func.max(PositionState.epoch)),
            portfolio_id=portfolio_id,
            as_of=as_of,
        )
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
            self._security_id_expr(PositionState.security_id).label("security_id"),
            PositionState.epoch.label("epoch"),
        )
        base_stmt = self._apply_reprocessing_key_scope(
            base_stmt,
            portfolio_id=portfolio_id,
            as_of=as_of,
        )
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count().filter(base_subq.c.status == "REPROCESSING").label("active_keys"),
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
                )
                .select_from(aggregate_subq)
                .outerjoin(oldest_key_subq, true())
            )
        ).one()
        return ReprocessingHealthSummary(
            active_keys=int(row.active_keys or 0),
            stale_reprocessing_keys=int(row.stale_reprocessing_keys or 0),
            oldest_reprocessing_watermark_date=row.oldest_reprocessing_watermark_date,
            oldest_reprocessing_security_id=normalize_security_id(row.security_id),
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
        stale_threshold, failed_since = support_job_health_thresholds(
            stale_minutes=stale_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=reference_now,
        )
        base_stmt = select(
            PortfolioValuationJob.status.label("status"),
            PortfolioValuationJob.updated_at.label("updated_at"),
            PortfolioValuationJob.valuation_date.label("valuation_date"),
            PortfolioValuationJob.id.label("id"),
            PortfolioValuationJob.correlation_id.label("correlation_id"),
            self._security_id_expr(PortfolioValuationJob.security_id).label("security_id"),
        )
        base_stmt = self._apply_valuation_job_scope(
            base_stmt,
            portfolio_id=portfolio_id,
            as_of=as_of,
        )
        return await self._get_support_job_health_summary(
            base_stmt,
            open_date_column_name="valuation_date",
            stale_threshold=stale_threshold,
            failed_since=failed_since,
            include_security=True,
        )

    async def get_aggregation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> JobHealthSummary:
        stale_threshold, failed_since = support_job_health_thresholds(
            stale_minutes=stale_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=reference_now,
        )
        base_stmt = select(
            PortfolioAggregationJob.status.label("status"),
            PortfolioAggregationJob.updated_at.label("updated_at"),
            PortfolioAggregationJob.aggregation_date.label("aggregation_date"),
            PortfolioAggregationJob.id.label("id"),
            PortfolioAggregationJob.correlation_id.label("correlation_id"),
        )
        base_stmt = self._apply_aggregation_job_scope(
            base_stmt,
            portfolio_id=portfolio_id,
            as_of=as_of,
        )
        return await self._get_support_job_health_summary(
            base_stmt,
            open_date_column_name="aggregation_date",
            stale_threshold=stale_threshold,
            failed_since=failed_since,
        )

    async def get_analytics_export_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: Optional[datetime] = None,
    ) -> ExportJobHealthSummary:
        stale_threshold, failed_since = support_job_health_thresholds(
            stale_minutes=stale_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=reference_now,
        )
        base_stmt = select(
            AnalyticsExportJob.status.label("status"),
            AnalyticsExportJob.updated_at.label("updated_at"),
            AnalyticsExportJob.created_at.label("created_at"),
            AnalyticsExportJob.job_id.label("job_id"),
            AnalyticsExportJob.request_fingerprint.label("request_fingerprint"),
        )
        base_stmt = self._apply_analytics_export_job_scope(
            base_stmt,
            portfolio_id=portfolio_id,
            as_of=as_of,
        )
        return await self._get_analytics_export_job_health_summary(
            base_stmt,
            stale_threshold=stale_threshold,
            failed_since=failed_since,
        )

    async def get_latest_transaction_date(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        stmt = self._latest_transaction_date_stmt(
            portfolio_id=portfolio_id,
            snapshot_as_of=as_of,
        )
        latest_transaction_at = (await self.db.execute(stmt)).scalar_one_or_none()
        return latest_transaction_at.date() if latest_transaction_at is not None else None

    async def get_latest_transaction_date_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: Optional[datetime] = None,
    ) -> Optional[date]:
        stmt = self._latest_transaction_date_stmt(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            snapshot_as_of=snapshot_as_of,
        )
        latest_transaction_at = (await self.db.execute(stmt)).scalar_one_or_none()
        return latest_transaction_at.date() if latest_transaction_at is not None else None

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
        stmt = self._current_epoch_snapshot_date_stmt(
            portfolio_id=portfolio_id,
            snapshot_as_of=as_of,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: Optional[datetime] = None,
    ) -> Optional[date]:
        stmt = self._current_epoch_snapshot_date_stmt(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            snapshot_as_of=snapshot_as_of,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_snapshot_history_mismatch_count(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> int:
        history_security_id = self._security_id_expr(PositionHistory.security_id)
        snapshot_security_id = self._security_id_expr(DailyPositionSnapshot.security_id)
        latest_history = select(
            PositionHistory.portfolio_id,
            history_security_id.label("security_id"),
            PositionHistory.epoch,
            func.max(PositionHistory.position_date).label("latest_history_date"),
        )
        latest_history = self._apply_current_position_history_scope(
            latest_history,
            portfolio_id=portfolio_id,
            position_history_security_id=history_security_id,
            history_as_of=as_of,
        )
        latest_history = latest_history.group_by(
            PositionHistory.portfolio_id, history_security_id, PositionHistory.epoch
        ).subquery()
        latest_snapshot = select(
            DailyPositionSnapshot.portfolio_id,
            snapshot_security_id.label("security_id"),
            DailyPositionSnapshot.epoch,
            func.max(DailyPositionSnapshot.date).label("latest_snapshot_date"),
        ).select_from(DailyPositionSnapshot)
        latest_snapshot = self._apply_current_epoch_snapshot_scope(
            latest_snapshot,
            portfolio_id=portfolio_id,
            snapshot_as_of=as_of,
        )
        latest_snapshot = latest_snapshot.group_by(
            DailyPositionSnapshot.portfolio_id,
            snapshot_security_id,
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

        stmt = select(
            func.count().label("total_positions"),
            func.count()
            .filter(
                DailyPositionSnapshot.valuation_status.is_not(None),
                DailyPositionSnapshot.valuation_status != "UNVALUED",
            )
            .label("valued_positions"),
        ).select_from(DailyPositionSnapshot)
        stmt = self._apply_current_epoch_snapshot_scope(
            stmt,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            snapshot_as_of=snapshot_as_of,
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
        base_subq = missing_historical_fx_base_stmt(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            snapshot_as_of=snapshot_as_of,
        ).subquery()

        aggregate_row = (
            await self.db.execute(missing_historical_fx_aggregate_stmt(base_subq))
        ).one()
        sample_rows = (
            await self.db.execute(
                missing_historical_fx_sample_stmt(
                    base_subq,
                    sample_limit=sample_limit,
                )
            )
        ).all()
        return missing_historical_fx_summary_from_rows(
            aggregate_row,
            sample_rows,
        )

    async def get_latest_financial_reconciliation_control_stage(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[PipelineStageState]:
        stmt = select(PipelineStageState).where(
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.stage_name == "FINANCIAL_RECONCILIATION",
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
        stmt = self._apply_reconciliation_run_scope(
            select(FinancialReconciliationRun),
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
            as_of=as_of,
            include_started_as_of=True,
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
        normalized_security_id = normalize_security_id(security_id)
        if not normalized_security_id:
            return None
        stmt = self._apply_reprocessing_key_scope(
            select(PositionState),
            portfolio_id=portfolio_id,
            normalized_security_id=normalized_security_id,
            as_of=as_of,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_position_history_date(
        self, portfolio_id: str, security_id: str, epoch: int, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        normalized_security_id = normalize_security_id(security_id)
        if not normalized_security_id:
            return None
        history_security_id = self._security_id_expr(PositionHistory.security_id)
        stmt = self._apply_portfolio_security_epoch_scope(
            select(func.max(PositionHistory.position_date)),
            PositionHistory,
            history_security_id,
            portfolio_id=portfolio_id,
            normalized_security_id=normalized_security_id,
            epoch=epoch,
            as_of=as_of,
            as_of_columns=(PositionHistory.created_at,),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_daily_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int, as_of: Optional[datetime] = None
    ) -> Optional[date]:
        normalized_security_id = normalize_security_id(security_id)
        if not normalized_security_id:
            return None
        snapshot_security_id = self._security_id_expr(DailyPositionSnapshot.security_id)
        stmt = self._apply_portfolio_security_epoch_scope(
            select(func.max(DailyPositionSnapshot.date)),
            DailyPositionSnapshot,
            snapshot_security_id,
            portfolio_id=portfolio_id,
            normalized_security_id=normalized_security_id,
            epoch=epoch,
            as_of=as_of,
            as_of_columns=(DailyPositionSnapshot.created_at,),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_valuation_job(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        as_of: Optional[datetime] = None,
    ) -> Optional[PortfolioValuationJob]:
        normalized_security_id = normalize_security_id(security_id)
        if not normalized_security_id:
            return None
        valuation_job_security_id = self._security_id_expr(PortfolioValuationJob.security_id)
        stmt = self._apply_portfolio_security_epoch_scope(
            select(PortfolioValuationJob),
            PortfolioValuationJob,
            valuation_job_security_id,
            portfolio_id=portfolio_id,
            normalized_security_id=normalized_security_id,
            epoch=epoch,
            as_of=as_of,
            as_of_columns=(PortfolioValuationJob.created_at, PortfolioValuationJob.updated_at),
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return 0
        stmt = self._apply_reprocessing_key_scope(
            select(func.count()).select_from(PositionState),
            portfolio_id=portfolio_id,
            status=reprocessing_status,
            normalized_security_id=normalized_security_id,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return []
        position_state_security_id = self._security_id_expr(PositionState.security_id)
        latest_position_history_date = self._lineage_latest_date_subquery(
            PositionHistory,
            PositionHistory.position_date,
            self._security_id_expr(PositionHistory.security_id),
            position_state_security_id,
            as_of_column=PositionHistory.created_at,
            as_of=as_of,
        )
        latest_daily_snapshot_date = self._lineage_latest_date_subquery(
            DailyPositionSnapshot,
            DailyPositionSnapshot.date,
            self._security_id_expr(DailyPositionSnapshot.security_id),
            position_state_security_id,
            as_of_column=DailyPositionSnapshot.created_at,
            as_of=as_of,
        )
        latest_valuation_job = self._latest_valuation_job_lateral(
            position_state_security_id,
            as_of,
        )
        latest_valuation_job_date = latest_valuation_job.c.latest_valuation_job_date
        latest_valuation_job_status = latest_valuation_job.c.latest_valuation_job_status
        has_artifact_gap = self._lineage_artifact_gap_case(
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        lineage_priority = self._lineage_priority_case(
            has_artifact_gap=has_artifact_gap,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        stmt = self._lineage_keys_select(
            position_state_security_id=position_state_security_id,
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job=latest_valuation_job,
        )
        stmt = self._apply_reprocessing_key_scope(
            stmt,
            portfolio_id=portfolio_id,
            status=reprocessing_status,
            normalized_security_id=normalized_security_id,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                lineage_priority.asc(),
                latest_position_history_date.desc().nullslast(),
                position_state_security_id.asc(),
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return 0
        stmt = self._apply_valuation_job_scope(
            select(func.count()).select_from(PortfolioValuationJob),
            portfolio_id=portfolio_id,
            status=status,
            business_date=business_date,
            normalized_security_id=normalized_security_id,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return []
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = self._apply_valuation_job_scope(
            select(PortfolioValuationJob),
            portfolio_id=portfolio_id,
            status=status,
            business_date=business_date,
            normalized_security_id=normalized_security_id,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
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
        stmt = self._apply_aggregation_job_scope(
            select(func.count()).select_from(PortfolioAggregationJob),
            portfolio_id=portfolio_id,
            status=status,
            business_date=business_date,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
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
        stmt = self._apply_aggregation_job_scope(
            select(PortfolioAggregationJob),
            portfolio_id=portfolio_id,
            status=status,
            business_date=business_date,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
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
        stmt = self._apply_analytics_export_job_scope(
            select(func.count()).select_from(AnalyticsExportJob),
            portfolio_id=portfolio_id,
            status=status,
            job_id=job_id,
            request_fingerprint=request_fingerprint,
            as_of=as_of,
        )
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
        stmt = self._apply_analytics_export_job_scope(
            select(AnalyticsExportJob),
            portfolio_id=portfolio_id,
            status=status,
            job_id=job_id,
            request_fingerprint=request_fingerprint,
            as_of=as_of,
        )
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
        stmt = self._apply_reconciliation_run_scope(
            select(func.count()).select_from(FinancialReconciliationRun),
            portfolio_id=portfolio_id,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
            reconciliation_type=reconciliation_type,
            status=status,
            as_of=as_of,
        )
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
        stmt = self._apply_reconciliation_run_scope(
            select(FinancialReconciliationRun),
            portfolio_id=portfolio_id,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
            dedupe_key=dedupe_key,
            reconciliation_type=reconciliation_type,
            status=status,
            as_of=as_of,
        )
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
        stmt = self._apply_reconciliation_run_scope(
            select(FinancialReconciliationRun),
            portfolio_id=portfolio_id,
            run_id=run_id,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return []
        severity = FinancialReconciliationFinding.severity
        severity_rank = case(
            (severity == "ERROR", 0),
            (severity == "WARNING", 1),
            (severity == "INFO", 2),
            else_=9,
        )
        stmt = self._apply_reconciliation_finding_scope(
            select(FinancialReconciliationFinding),
            run_id=run_id,
            finding_id=finding_id,
            normalized_security_id=normalized_security_id,
            transaction_id=transaction_id,
            as_of=as_of,
        )
        stmt = stmt.order_by(
            severity_rank.asc(),
            FinancialReconciliationFinding.finding_type.asc(),
            FinancialReconciliationFinding.created_at.desc(),
            FinancialReconciliationFinding.id.asc(),
        ).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_reconciliation_findings_count(
        self,
        run_id: str,
        finding_id: Optional[str] = None,
        security_id: Optional[str] = None,
        transaction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return 0
        stmt = self._apply_reconciliation_finding_scope(
            select(func.count()).select_from(FinancialReconciliationFinding),
            run_id=run_id,
            finding_id=finding_id,
            normalized_security_id=normalized_security_id,
            transaction_id=transaction_id,
            as_of=as_of,
        )
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
            self._security_id_expr(FinancialReconciliationFinding.security_id).label("security_id"),
            FinancialReconciliationFinding.transaction_id.label("transaction_id"),
        )
        base_stmt = self._apply_reconciliation_finding_scope(
            base_stmt,
            run_id=run_id,
            as_of=as_of,
        )
        base_subq = base_stmt.subquery()
        aggregate_subq = (
            select(
                func.count().label("total_findings"),
                func.count().filter(base_subq.c.severity == "ERROR").label("blocking_findings"),
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
                )
                .select_from(aggregate_subq)
                .outerjoin(top_blocking_subq, true())
            )
        ).one()
        return ReconciliationFindingSummary(
            total_findings=int(row.total_findings or 0),
            blocking_findings=int(row.blocking_findings or 0),
            top_blocking_finding_id=row.finding_id,
            top_blocking_finding_type=row.finding_type,
            top_blocking_finding_security_id=normalize_security_id(row.security_id),
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
        stmt = self._apply_portfolio_control_stage_scope(
            select(func.count()).select_from(PipelineStageState),
            portfolio_id=portfolio_id,
            stage_id=stage_id,
            stage_name=stage_name,
            business_date=business_date,
            status=status,
            as_of=as_of,
        )
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
        stmt = self._apply_portfolio_control_stage_scope(
            select(PipelineStageState),
            portfolio_id=portfolio_id,
            stage_id=stage_id,
            stage_name=stage_name,
            business_date=business_date,
            status=status,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return 0
        stmt = self._apply_reprocessing_key_scope(
            select(func.count()).select_from(PositionState),
            portfolio_id=portfolio_id,
            status=status,
            normalized_security_id=normalized_security_id,
            watermark_date=watermark_date,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return []
        state_security_id = self._security_id_expr(PositionState.security_id)
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = self._apply_reprocessing_key_scope(
            select(PositionState),
            portfolio_id=portfolio_id,
            status=status,
            normalized_security_id=normalized_security_id,
            watermark_date=watermark_date,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                self._reprocessing_key_priority(
                    PositionState.status,
                    PositionState.updated_at,
                    stale_threshold,
                ).asc(),
                PositionState.updated_at.asc(),
                state_security_id.asc(),
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return 0
        reset_scope = self._reset_watermark_reprocessing_job_scope(portfolio_id)
        stmt = self._apply_reprocessing_job_scope(
            select(func.count()).select_from(ReprocessingJob),
            reset_scope=reset_scope,
            status=status,
            normalized_security_id=normalized_security_id,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
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
        normalized_security_id = (
            normalize_security_id(security_id) if security_id is not None else None
        )
        if security_id is not None and not normalized_security_id:
            return []
        reset_scope = self._reset_watermark_reprocessing_job_scope(portfolio_id)
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = self._apply_reprocessing_job_scope(
            select(
                ReprocessingJob.id,
                ReprocessingJob.job_type,
                reset_scope.impacted_date_expr.label("business_date"),
                ReprocessingJob.status,
                reset_scope.security_id_expr.label("security_id"),
                ReprocessingJob.attempt_count,
                ReprocessingJob.correlation_id,
                ReprocessingJob.created_at,
                ReprocessingJob.updated_at,
                ReprocessingJob.failure_reason,
            ),
            reset_scope=reset_scope,
            status=status,
            normalized_security_id=normalized_security_id,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                self._support_job_priority(
                    ReprocessingJob.status,
                    ReprocessingJob.updated_at,
                    stale_threshold,
                ).asc(),
                reset_scope.impacted_date_expr.asc(),
                ReprocessingJob.created_at.asc(),
                ReprocessingJob.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).all())
