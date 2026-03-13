import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import (
    AnalyticsExportJobListResponse,
    AnalyticsExportJobRecord,
    CalculatorSloBucket,
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageKeyRecord,
    LineageResponse,
    ReconciliationFindingListResponse,
    ReconciliationFindingRecord,
    ReconciliationRunListResponse,
    ReconciliationRunRecord,
    ReprocessingSloBucket,
    SupportJobListResponse,
    SupportJobRecord,
    SupportOverviewResponse,
)
from ..repositories.operations_repository import OperationsRepository


class OperationsService:
    SUPPORT_JOB_STALE_THRESHOLD = timedelta(minutes=15)

    def __init__(self, db: AsyncSession):
        self.repo = OperationsRepository(db)

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

    async def get_support_overview(self, portfolio_id: str) -> SupportOverviewResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        (
            latest_business_date,
            current_epoch,
            active_reprocessing_keys,
            valuation_job_health,
            aggregation_job_health,
            analytics_export_job_health,
            latest_transaction_date,
            latest_position_snapshot_date_unbounded,
            position_snapshot_history_mismatch_count,
            latest_control_stage,
        ) = await asyncio.gather(
            self.repo.get_latest_business_date(),
            self.repo.get_current_portfolio_epoch(portfolio_id),
            self.repo.get_active_reprocessing_keys_count(portfolio_id),
            self.repo.get_valuation_job_health_summary(
                portfolio_id, stale_minutes=15, failed_window_hours=24
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id, stale_minutes=15, failed_window_hours=24
            ),
            self.repo.get_analytics_export_job_health_summary(
                portfolio_id, stale_minutes=15, failed_window_hours=24
            ),
            self.repo.get_latest_transaction_date(portfolio_id),
            self.repo.get_latest_snapshot_date_for_current_epoch(portfolio_id),
            self.repo.get_position_snapshot_history_mismatch_count(portfolio_id),
            self.repo.get_latest_financial_reconciliation_control_stage(portfolio_id),
        )

        latest_booked_transaction_date = None
        latest_booked_position_snapshot_date = None
        if latest_business_date is not None:
            (
                latest_booked_transaction_date,
                latest_booked_position_snapshot_date,
            ) = await asyncio.gather(
                self.repo.get_latest_transaction_date_as_of(portfolio_id, latest_business_date),
                self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                    portfolio_id, latest_business_date
                ),
            )

        valuation_backlog_age_days = None
        if valuation_job_health.oldest_open_job_date:
            reference_date = latest_business_date or datetime.now(timezone.utc).date()
            valuation_backlog_age_days = max(
                0, (reference_date - valuation_job_health.oldest_open_job_date).days
            )
        aggregation_backlog_age_days = None
        if aggregation_job_health.oldest_open_job_date:
            reference_date = latest_business_date or datetime.now(timezone.utc).date()
            aggregation_backlog_age_days = max(
                0, (reference_date - aggregation_job_health.oldest_open_job_date).days
            )
        analytics_export_backlog_age_minutes = None
        if analytics_export_job_health.oldest_open_job_created_at:
            delta = (
                datetime.now(timezone.utc) - analytics_export_job_health.oldest_open_job_created_at
            )
            analytics_export_backlog_age_minutes = max(0, int(delta.total_seconds() // 60))

        controls_status = latest_control_stage.status if latest_control_stage else None
        controls_blocking = self._is_controls_blocking(controls_status)

        return SupportOverviewResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            current_epoch=current_epoch,
            active_reprocessing_keys=active_reprocessing_keys,
            pending_valuation_jobs=valuation_job_health.pending_jobs,
            processing_valuation_jobs=valuation_job_health.processing_jobs,
            stale_processing_valuation_jobs=valuation_job_health.stale_processing_jobs,
            failed_valuation_jobs=valuation_job_health.failed_jobs,
            oldest_pending_valuation_date=valuation_job_health.oldest_open_job_date,
            valuation_backlog_age_days=valuation_backlog_age_days,
            pending_aggregation_jobs=aggregation_job_health.pending_jobs,
            processing_aggregation_jobs=aggregation_job_health.processing_jobs,
            stale_processing_aggregation_jobs=aggregation_job_health.stale_processing_jobs,
            failed_aggregation_jobs=aggregation_job_health.failed_jobs,
            oldest_pending_aggregation_date=aggregation_job_health.oldest_open_job_date,
            aggregation_backlog_age_days=aggregation_backlog_age_days,
            pending_analytics_export_jobs=analytics_export_job_health.accepted_jobs,
            processing_analytics_export_jobs=analytics_export_job_health.running_jobs,
            stale_processing_analytics_export_jobs=analytics_export_job_health.stale_running_jobs,
            failed_analytics_export_jobs=analytics_export_job_health.failed_jobs,
            oldest_pending_analytics_export_created_at=(
                analytics_export_job_health.oldest_open_job_created_at
            ),
            analytics_export_backlog_age_minutes=analytics_export_backlog_age_minutes,
            latest_transaction_date=latest_transaction_date,
            latest_booked_transaction_date=latest_booked_transaction_date,
            latest_position_snapshot_date=latest_position_snapshot_date_unbounded,
            latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
            position_snapshot_history_mismatch_count=position_snapshot_history_mismatch_count,
            controls_business_date=(
                latest_control_stage.business_date if latest_control_stage else None
            ),
            controls_epoch=latest_control_stage.epoch if latest_control_stage else None,
            controls_status=controls_status,
            controls_blocking=controls_blocking,
            publish_allowed=not controls_blocking,
        )

    @staticmethod
    def _is_controls_blocking(status: str | None) -> bool:
        return status in {"FAILED", "REQUIRES_REPLAY"}

    async def get_calculator_slos(
        self, portfolio_id: str, stale_threshold_minutes: int = 15
    ) -> CalculatorSloResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        (
            latest_business_date,
            active_reprocessing_keys,
            valuation_job_health,
            aggregation_job_health,
        ) = await asyncio.gather(
            self.repo.get_latest_business_date(),
            self.repo.get_active_reprocessing_keys_count(portfolio_id),
            self.repo.get_valuation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=24,
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=24,
            ),
        )

        reference_date = latest_business_date or datetime.now(timezone.utc).date()
        valuation_backlog_age_days = (
            max(0, (reference_date - valuation_job_health.oldest_open_job_date).days)
            if valuation_job_health.oldest_open_job_date is not None
            else None
        )
        aggregation_backlog_age_days = (
            max(0, (reference_date - aggregation_job_health.oldest_open_job_date).days)
            if aggregation_job_health.oldest_open_job_date is not None
            else None
        )

        return CalculatorSloResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=datetime.now(timezone.utc),
            valuation=CalculatorSloBucket(
                pending_jobs=valuation_job_health.pending_jobs,
                processing_jobs=valuation_job_health.processing_jobs,
                stale_processing_jobs=valuation_job_health.stale_processing_jobs,
                failed_jobs=valuation_job_health.failed_jobs,
                failed_jobs_last_24h=valuation_job_health.failed_jobs_last_hours,
                oldest_open_job_date=valuation_job_health.oldest_open_job_date,
                backlog_age_days=valuation_backlog_age_days,
            ),
            aggregation=CalculatorSloBucket(
                pending_jobs=aggregation_job_health.pending_jobs,
                processing_jobs=aggregation_job_health.processing_jobs,
                stale_processing_jobs=aggregation_job_health.stale_processing_jobs,
                failed_jobs=aggregation_job_health.failed_jobs,
                failed_jobs_last_24h=aggregation_job_health.failed_jobs_last_hours,
                oldest_open_job_date=aggregation_job_health.oldest_open_job_date,
                backlog_age_days=aggregation_backlog_age_days,
            ),
            reprocessing=ReprocessingSloBucket(active_reprocessing_keys=active_reprocessing_keys),
        )

    async def get_lineage(self, portfolio_id: str, security_id: str) -> LineageResponse:
        position_state = await self.repo.get_position_state(portfolio_id, security_id)
        if not position_state:
            raise ValueError(
                "Lineage state not found for portfolio "
                f"'{portfolio_id}' and security '{security_id}'"
            )

        (
            latest_history_date,
            latest_snapshot_date,
            latest_valuation_job,
        ) = await asyncio.gather(
            self.repo.get_latest_position_history_date(
                portfolio_id, security_id, position_state.epoch
            ),
            self.repo.get_latest_daily_snapshot_date(
                portfolio_id, security_id, position_state.epoch
            ),
            self.repo.get_latest_valuation_job(portfolio_id, security_id, position_state.epoch),
        )

        return LineageResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=position_state.epoch,
            watermark_date=position_state.watermark_date,
            reprocessing_status=position_state.status,
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=(
                latest_valuation_job.valuation_date if latest_valuation_job else None
            ),
            latest_valuation_job_status=(
                latest_valuation_job.status if latest_valuation_job else None
            ),
        )

    async def get_lineage_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        reprocessing_status: str | None = None,
        security_id: str | None = None,
    ) -> LineageKeyListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, keys = await asyncio.gather(
            self.repo.get_lineage_keys_count(
                portfolio_id=portfolio_id,
                reprocessing_status=reprocessing_status,
                security_id=security_id,
            ),
            self.repo.get_lineage_keys(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                reprocessing_status=reprocessing_status,
                security_id=security_id,
            ),
        )
        return LineageKeyListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                LineageKeyRecord(
                    security_id=k.security_id,
                    epoch=k.epoch,
                    watermark_date=k.watermark_date,
                    reprocessing_status=k.status,
                )
                for k in keys
            ],
        )

    async def get_valuation_jobs(
        self, portfolio_id: str, skip: int, limit: int, status: str | None = None
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, jobs = await asyncio.gather(
            self.repo.get_valuation_jobs_count(portfolio_id=portfolio_id, status=status),
            self.repo.get_valuation_jobs(
                portfolio_id=portfolio_id, skip=skip, limit=limit, status=status
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                SupportJobRecord(
                    job_type="VALUATION",
                    business_date=job.valuation_date,
                    status=job.status,
                    security_id=job.security_id,
                    epoch=job.epoch,
                    attempt_count=job.attempt_count,
                    updated_at=job.updated_at,
                    is_stale_processing=self._is_support_job_stale(job.status, job.updated_at),
                    failure_reason=job.failure_reason,
                )
                for job in jobs
            ],
        )

    async def get_aggregation_jobs(
        self, portfolio_id: str, skip: int, limit: int, status: str | None = None
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, jobs = await asyncio.gather(
            self.repo.get_aggregation_jobs_count(portfolio_id=portfolio_id, status=status),
            self.repo.get_aggregation_jobs(
                portfolio_id=portfolio_id, skip=skip, limit=limit, status=status
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                SupportJobRecord(
                    job_type="AGGREGATION",
                    business_date=job.aggregation_date,
                    status=job.status,
                    security_id=None,
                    epoch=None,
                    attempt_count=job.attempt_count,
                    updated_at=job.updated_at,
                    is_stale_processing=self._is_support_job_stale(job.status, job.updated_at),
                    failure_reason=job.failure_reason,
                )
                for job in jobs
            ],
        )

    async def get_analytics_export_jobs(
        self, portfolio_id: str, skip: int, limit: int, status: str | None = None
    ) -> AnalyticsExportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, jobs = await asyncio.gather(
            self.repo.get_analytics_export_jobs_count(portfolio_id=portfolio_id, status=status),
            self.repo.get_analytics_export_jobs(
                portfolio_id=portfolio_id, skip=skip, limit=limit, status=status
            ),
        )
        return AnalyticsExportJobListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                AnalyticsExportJobRecord(
                    job_id=job.job_id,
                    dataset_type=job.dataset_type,
                    status=job.status,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    updated_at=job.updated_at,
                    is_stale_running=self._is_analytics_export_job_stale(
                        job.status, job.updated_at
                    ),
                    backlog_age_minutes=self._get_analytics_export_backlog_age_minutes(
                        job.status, job.created_at
                    ),
                    result_row_count=job.result_row_count,
                    error_message=job.error_message,
                )
                for job in jobs
            ],
        )

    async def get_reconciliation_runs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        reconciliation_type: str | None = None,
        status: str | None = None,
    ) -> ReconciliationRunListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, runs = await asyncio.gather(
            self.repo.get_reconciliation_runs_count(
                portfolio_id=portfolio_id,
                reconciliation_type=reconciliation_type,
                status=status,
            ),
            self.repo.get_reconciliation_runs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                reconciliation_type=reconciliation_type,
                status=status,
            ),
        )
        return ReconciliationRunListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                ReconciliationRunRecord(
                    run_id=run.run_id,
                    reconciliation_type=run.reconciliation_type,
                    status=run.status,
                    business_date=run.business_date,
                    epoch=run.epoch,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    failure_reason=run.failure_reason,
                    is_blocking=self._is_controls_blocking(run.status),
                )
                for run in runs
            ],
        )

    async def get_reconciliation_findings(
        self, portfolio_id: str, run_id: str, limit: int
    ) -> ReconciliationFindingListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        run = await self.repo.get_reconciliation_run(portfolio_id=portfolio_id, run_id=run_id)
        if run is None:
            raise ValueError(f"Reconciliation run {run_id} not found for portfolio {portfolio_id}")
        total, findings = await asyncio.gather(
            self.repo.get_reconciliation_findings_count(run_id=run_id),
            self.repo.get_reconciliation_findings(run_id=run_id, limit=limit),
        )
        return ReconciliationFindingListResponse(
            run_id=run_id,
            total=total,
            items=[
                ReconciliationFindingRecord(
                    finding_id=finding.finding_id,
                    finding_type=finding.finding_type,
                    severity=finding.severity,
                    security_id=finding.security_id,
                    transaction_id=finding.transaction_id,
                    business_date=finding.business_date,
                    epoch=finding.epoch,
                    created_at=finding.created_at,
                    detail=finding.detail,
                )
                for finding in findings
            ],
        )

    @classmethod
    def _is_support_job_stale(
        cls, status: str | None, updated_at: datetime | None, now: datetime | None = None
    ) -> bool:
        if status != "PROCESSING" or updated_at is None:
            return False
        reference_now = now or datetime.now(timezone.utc)
        return updated_at < reference_now - cls.SUPPORT_JOB_STALE_THRESHOLD

    @classmethod
    def _is_analytics_export_job_stale(
        cls, status: str | None, updated_at: datetime | None, now: datetime | None = None
    ) -> bool:
        normalized_status = "PROCESSING" if status == "running" else status
        return cls._is_support_job_stale(normalized_status, updated_at, now)

    @staticmethod
    def _get_analytics_export_backlog_age_minutes(
        status: str | None, created_at: datetime | None, now: datetime | None = None
    ) -> int | None:
        if status not in {"accepted", "running"} or created_at is None:
            return None
        reference_now = now or datetime.now(timezone.utc)
        return max(0, int((reference_now - created_at).total_seconds() // 60))
