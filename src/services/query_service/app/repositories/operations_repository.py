from datetime import date, datetime, timedelta, timezone
from typing import Optional

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from portfolio_common.database_models import (
    AnalyticsExportJob,
    BusinessDate,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    OutboxEvent,
    PipelineStageState,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    ReprocessingJob,
)
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from .identifier_normalization import normalize_security_id
from .operations_analytics_export_queries import (
    analytics_export_job_priority,
    apply_analytics_export_job_scope,
)
from .operations_health_queries import (
    analytics_export_job_health_aggregate,
    analytics_export_job_health_result_select,
    analytics_export_job_health_summary_from_row,
    oldest_open_analytics_export_job,
    oldest_open_support_job,
    support_job_health_aggregate,
    support_job_health_result_select,
    support_job_health_summary_from_row,
    support_job_health_thresholds,
)
from .operations_lineage_queries import (
    lineage_artifact_gap_case,
    lineage_keys_select,
    lineage_latest_date_subquery,
    lineage_priority_case,
)
from .operations_load_run_queries import (
    load_run_progress_execute_statements,
    load_run_progress_scalar_statements,
    load_run_progress_summary_from_rows,
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
    SnapshotValuationCoverageSummary,
)
from .operations_portfolio_control_queries import (
    apply_portfolio_control_stage_scope,
    portfolio_control_stage_priority,
)
from .operations_position_scope_queries import (
    apply_current_epoch_snapshot_scope,
    apply_current_position_history_scope,
    apply_portfolio_security_epoch_scope,
    current_epoch_snapshot_date_stmt,
    latest_transaction_date_stmt,
    security_id_expr,
)
from .operations_reconciliation_finding_queries import (
    apply_reconciliation_finding_scope,
    reconciliation_finding_severity_rank,
    reconciliation_finding_summary_base_select,
    reconciliation_finding_summary_from_row,
    reconciliation_finding_summary_select,
)
from .operations_reconciliation_run_queries import (
    apply_reconciliation_run_scope,
    reconciliation_run_priority,
)
from .operations_reprocessing_queries import (
    apply_reprocessing_job_scope,
    apply_reprocessing_key_scope,
    reprocessing_key_priority,
    reset_watermark_reprocessing_job_scope,
)
from .operations_support_job_queries import (
    apply_aggregation_job_scope,
    apply_valuation_job_scope,
    has_superseding_valuation_epoch,
    is_actionable_valuation_job,
    latest_valuation_job_lateral,
    support_job_priority,
)


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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
        scalar_statements = load_run_progress_scalar_statements(
            portfolio_pattern=portfolio_pattern,
            transaction_pattern=transaction_pattern,
            business_date=business_date,
            as_of=as_of,
            has_superseding_valuation_epoch=has_superseding_valuation_epoch(as_of=as_of),
        )
        execute_statements = load_run_progress_execute_statements(
            portfolio_pattern=portfolio_pattern,
            as_of=as_of,
            actionable_valuation_job=is_actionable_valuation_job(as_of=as_of),
            has_superseding_valuation_epoch=has_superseding_valuation_epoch(as_of=as_of),
        )

        scalar_values = [await self.db.scalar(stmt) for stmt in scalar_statements]
        execute_rows = [(await self.db.execute(stmt)).one() for stmt in execute_statements]
        return load_run_progress_summary_from_rows(
            scalar_values=scalar_values,
            valuation_summary=execute_rows[0],
            aggregation_summary=execute_rows[1],
            valuation_handoff_latency=execute_rows[2],
            valuation_without_position_timeseries=execute_rows[3],
        )

    async def get_current_portfolio_epoch(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> Optional[int]:
        stmt = apply_reprocessing_key_scope(
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
            security_id_expr(PositionState.security_id).label("security_id"),
            PositionState.epoch.label("epoch"),
        )
        base_stmt = apply_reprocessing_key_scope(
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
            security_id_expr(PortfolioValuationJob.security_id).label("security_id"),
        )
        base_stmt = apply_valuation_job_scope(
            base_stmt,
            portfolio_id=portfolio_id,
            actionable_valuation_job=is_actionable_valuation_job(as_of=as_of),
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
        base_stmt = apply_aggregation_job_scope(
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
        base_stmt = apply_analytics_export_job_scope(
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
        stmt = latest_transaction_date_stmt(
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
        stmt = latest_transaction_date_stmt(
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
        stmt = current_epoch_snapshot_date_stmt(
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
        stmt = current_epoch_snapshot_date_stmt(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            snapshot_as_of=snapshot_as_of,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_snapshot_history_mismatch_count(
        self, portfolio_id: str, as_of: Optional[datetime] = None
    ) -> int:
        history_security_id = security_id_expr(PositionHistory.security_id)
        snapshot_security_id = security_id_expr(DailyPositionSnapshot.security_id)
        latest_history = select(
            PositionHistory.portfolio_id,
            history_security_id.label("security_id"),
            PositionHistory.epoch,
            func.max(PositionHistory.position_date).label("latest_history_date"),
        )
        latest_history = apply_current_position_history_scope(
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
        latest_snapshot = apply_current_epoch_snapshot_scope(
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
        stmt = apply_current_epoch_snapshot_scope(
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
        stmt = apply_reconciliation_run_scope(
            select(FinancialReconciliationRun),
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
            as_of=as_of,
            include_started_as_of=True,
        )
        stmt = stmt.order_by(
            reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
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
        stmt = apply_reprocessing_key_scope(
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
        history_security_id = security_id_expr(PositionHistory.security_id)
        stmt = apply_portfolio_security_epoch_scope(
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
        snapshot_security_id = security_id_expr(DailyPositionSnapshot.security_id)
        stmt = apply_portfolio_security_epoch_scope(
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
        valuation_job_security_id = security_id_expr(PortfolioValuationJob.security_id)
        stmt = apply_portfolio_security_epoch_scope(
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
        stmt = apply_reprocessing_key_scope(
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
        position_state_security_id = security_id_expr(PositionState.security_id)
        latest_position_history_date = lineage_latest_date_subquery(
            PositionHistory,
            PositionHistory.position_date,
            security_id_expr(PositionHistory.security_id),
            position_state_security_id,
            as_of_column=PositionHistory.created_at,
            as_of=as_of,
        )
        latest_daily_snapshot_date = lineage_latest_date_subquery(
            DailyPositionSnapshot,
            DailyPositionSnapshot.date,
            security_id_expr(DailyPositionSnapshot.security_id),
            position_state_security_id,
            as_of_column=DailyPositionSnapshot.created_at,
            as_of=as_of,
        )
        latest_valuation_job = latest_valuation_job_lateral(
            position_state_security_id,
            as_of,
        )
        latest_valuation_job_date = latest_valuation_job.c.latest_valuation_job_date
        latest_valuation_job_status = latest_valuation_job.c.latest_valuation_job_status
        has_artifact_gap = lineage_artifact_gap_case(
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        lineage_priority = lineage_priority_case(
            has_artifact_gap=has_artifact_gap,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        stmt = lineage_keys_select(
            position_state_security_id=position_state_security_id,
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job=latest_valuation_job,
        )
        stmt = apply_reprocessing_key_scope(
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
        stmt = apply_valuation_job_scope(
            select(func.count()).select_from(PortfolioValuationJob),
            portfolio_id=portfolio_id,
            actionable_valuation_job=is_actionable_valuation_job(as_of=as_of),
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
        stmt = apply_valuation_job_scope(
            select(PortfolioValuationJob),
            portfolio_id=portfolio_id,
            actionable_valuation_job=is_actionable_valuation_job(as_of=as_of),
            status=status,
            business_date=business_date,
            normalized_security_id=normalized_security_id,
            job_id=job_id,
            correlation_id=correlation_id,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                support_job_priority(
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
        stmt = apply_aggregation_job_scope(
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
        stmt = apply_aggregation_job_scope(
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
                support_job_priority(
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
        stmt = apply_analytics_export_job_scope(
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
        stmt = apply_analytics_export_job_scope(
            select(AnalyticsExportJob),
            portfolio_id=portfolio_id,
            status=status,
            job_id=job_id,
            request_fingerprint=request_fingerprint,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                analytics_export_job_priority(
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

    def _failed_outbox_events_stmt(
        self,
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        topic: Optional[str] = None,
        correlation_id: Optional[str] = None,
        reason_code: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ):
        stmt = select(OutboxEvent).where(OutboxEvent.status == "FAILED")
        if aggregate_type is not None:
            stmt = stmt.where(OutboxEvent.aggregate_type == aggregate_type)
        if aggregate_id is not None:
            stmt = stmt.where(OutboxEvent.aggregate_id == aggregate_id)
        if event_type is not None:
            stmt = stmt.where(OutboxEvent.event_type == event_type)
        if topic is not None:
            stmt = stmt.where(OutboxEvent.topic == topic)
        if correlation_id is not None:
            stmt = stmt.where(OutboxEvent.correlation_id == correlation_id)
        if reason_code is not None:
            stmt = stmt.where(OutboxEvent.last_failure_reason_code == reason_code)
        if as_of is not None:
            stmt = stmt.where(
                OutboxEvent.created_at <= as_of,
                or_(OutboxEvent.last_failure_at.is_(None), OutboxEvent.last_failure_at <= as_of),
            )
        return stmt

    async def get_failed_outbox_events_count(
        self,
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        topic: Optional[str] = None,
        correlation_id: Optional[str] = None,
        reason_code: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        base_stmt = self._failed_outbox_events_stmt(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            topic=topic,
            correlation_id=correlation_id,
            reason_code=reason_code,
            as_of=as_of,
        ).subquery()
        return int(
            (await self.db.execute(select(func.count()).select_from(base_stmt))).scalar_one() or 0
        )

    async def get_failed_outbox_events(
        self,
        *,
        skip: int,
        limit: int,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        event_type: Optional[str] = None,
        topic: Optional[str] = None,
        correlation_id: Optional[str] = None,
        reason_code: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[OutboxEvent]:
        stmt = self._failed_outbox_events_stmt(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            topic=topic,
            correlation_id=correlation_id,
            reason_code=reason_code,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                OutboxEvent.last_failure_at.desc().nullslast(),
                OutboxEvent.last_attempted_at.desc().nullslast(),
                OutboxEvent.created_at.desc(),
                OutboxEvent.id.asc(),
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
        stmt = apply_reconciliation_run_scope(
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
        stmt = apply_reconciliation_run_scope(
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
                reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
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
        stmt = apply_reconciliation_run_scope(
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
        stmt = apply_reconciliation_finding_scope(
            select(FinancialReconciliationFinding),
            run_id=run_id,
            finding_id=finding_id,
            normalized_security_id=normalized_security_id,
            transaction_id=transaction_id,
            as_of=as_of,
        )
        stmt = stmt.order_by(
            reconciliation_finding_severity_rank().asc(),
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
        stmt = apply_reconciliation_finding_scope(
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
        base_stmt = apply_reconciliation_finding_scope(
            reconciliation_finding_summary_base_select(),
            run_id=run_id,
            as_of=as_of,
        )
        row = (await self.db.execute(reconciliation_finding_summary_select(base_stmt))).one()
        return reconciliation_finding_summary_from_row(row)

    async def get_portfolio_control_stages_count(
        self,
        portfolio_id: str,
        stage_id: Optional[int] = None,
        stage_name: Optional[str] = None,
        business_date: Optional[date] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        stmt = apply_portfolio_control_stage_scope(
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
        stmt = apply_portfolio_control_stage_scope(
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
                portfolio_control_stage_priority(PipelineStageState.status).asc(),
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
        stmt = apply_reprocessing_key_scope(
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
        state_security_id = security_id_expr(PositionState.security_id)
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = apply_reprocessing_key_scope(
            select(PositionState),
            portfolio_id=portfolio_id,
            status=status,
            normalized_security_id=normalized_security_id,
            watermark_date=watermark_date,
            as_of=as_of,
        )
        stmt = (
            stmt.order_by(
                reprocessing_key_priority(
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
        reset_scope = reset_watermark_reprocessing_job_scope(portfolio_id)
        stmt = apply_reprocessing_job_scope(
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
        reset_scope = reset_watermark_reprocessing_job_scope(portfolio_id)
        reference_now = reference_now or datetime.now(timezone.utc)
        stale_threshold = reference_now - timedelta(minutes=stale_minutes)
        stmt = apply_reprocessing_job_scope(
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
                support_job_priority(
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
