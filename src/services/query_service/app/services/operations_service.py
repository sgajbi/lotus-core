import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import (
    AnalyticsExportJobListResponse,
    AnalyticsExportJobRecord,
    CalculatorSloBucket,
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageKeyRecord,
    LineageResponse,
    PortfolioControlStageListResponse,
    PortfolioControlStageRecord,
    ReconciliationFindingListResponse,
    ReconciliationFindingRecord,
    ReconciliationRunListResponse,
    ReconciliationRunRecord,
    ReprocessingKeyListResponse,
    ReprocessingKeyRecord,
    ReprocessingSloBucket,
    SupportJobListResponse,
    SupportJobRecord,
    SupportOverviewResponse,
)
from ..repositories.operations_repository import OperationsRepository, ReconciliationFindingSummary
from ..support_policy import (
    DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
)


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.repo = OperationsRepository(db)

    @classmethod
    def _get_support_job_operational_state(
        cls,
        status: str,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        if status == "FAILED":
            return "FAILED"
        if cls._is_support_job_stale(status, updated_at, now, stale_threshold_minutes):
            return "STALE_PROCESSING"
        if status == "PROCESSING":
            return "PROCESSING"
        if status == "PENDING":
            return "PENDING"
        return "COMPLETED"

    @staticmethod
    def _is_support_job_retrying(status: str, attempt_count: int | None) -> bool:
        return (attempt_count or 0) > 0 and status in {"PENDING", "PROCESSING"}

    @staticmethod
    def _normalize_analytics_export_status(status: str | None) -> str | None:
        if status is None:
            return None
        return status.lower()

    @classmethod
    def _get_analytics_export_operational_state(
        cls,
        status: str,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        status = cls._normalize_analytics_export_status(status) or ""
        if status == "failed":
            return "FAILED"
        if cls._is_analytics_export_job_stale(
            status, updated_at, now, stale_threshold_minutes
        ):
            return "STALE_RUNNING"
        if status == "running":
            return "RUNNING"
        if status == "accepted":
            return "ACCEPTED"
        return "COMPLETED"

    @classmethod
    def _get_reconciliation_operational_state(cls, status: str | None) -> str:
        if cls._is_controls_blocking(status):
            return "BLOCKING"
        if status == "RUNNING":
            return "RUNNING"
        return "COMPLETED"

    @classmethod
    def _get_portfolio_control_stage_operational_state(cls, status: str | None) -> str:
        return "BLOCKING" if cls._is_controls_blocking(status) else "COMPLETED"

    @staticmethod
    def _is_reconciliation_finding_blocking(severity: str | None) -> bool:
        return severity == "ERROR"

    @classmethod
    def _get_reconciliation_finding_operational_state(cls, severity: str | None) -> str:
        return "BLOCKING" if cls._is_reconciliation_finding_blocking(severity) else "NON_BLOCKING"

    @classmethod
    def _get_reprocessing_key_operational_state(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        if cls._is_reprocessing_key_stale(
            status, updated_at, now, stale_threshold_minutes
        ):
            return "STALE_REPROCESSING"
        if status == "REPROCESSING":
            return "REPROCESSING"
        return "CURRENT"

    @staticmethod
    def _has_lineage_artifact_gap(
        latest_position_history_date: date | None,
        latest_daily_snapshot_date: date | None,
        latest_valuation_job_date: date | None,
        latest_valuation_job_status: str | None,
    ) -> bool:
        if latest_position_history_date is None:
            return False
        if (
            latest_daily_snapshot_date is None
            or latest_daily_snapshot_date < latest_position_history_date
        ):
            return True
        if (
            latest_valuation_job_date is None
            or latest_valuation_job_date < latest_position_history_date
        ):
            return True
        return latest_valuation_job_status in {"FAILED", "PENDING", "PROCESSING"}

    @staticmethod
    def _get_lineage_key_operational_state(
        reprocessing_status: str | None,
        has_artifact_gap: bool,
        latest_valuation_job_status: str | None,
    ) -> str:
        if reprocessing_status == "REPROCESSING":
            return "REPLAYING"
        if has_artifact_gap:
            if latest_valuation_job_status == "FAILED":
                return "VALUATION_BLOCKED"
            return "ARTIFACT_GAP"
        return "HEALTHY"

    def _build_lineage_key_record(self, key: dict[str, object]) -> LineageKeyRecord:
        latest_position_history_date = key["latest_position_history_date"]
        latest_daily_snapshot_date = key["latest_daily_snapshot_date"]
        latest_valuation_job_date = key["latest_valuation_job_date"]
        latest_valuation_job_status = key["latest_valuation_job_status"]
        has_artifact_gap = self._has_lineage_artifact_gap(
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        return LineageKeyRecord(
            security_id=key["security_id"],
            epoch=key["epoch"],
            watermark_date=key["watermark_date"],
            reprocessing_status=key["reprocessing_status"],
            latest_position_history_date=latest_position_history_date,
            latest_daily_snapshot_date=latest_daily_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_id=key["latest_valuation_job_id"],
            latest_valuation_job_status=latest_valuation_job_status,
            latest_valuation_job_correlation_id=key["latest_valuation_job_correlation_id"],
            has_artifact_gap=has_artifact_gap,
            operational_state=self._get_lineage_key_operational_state(
                reprocessing_status=key["reprocessing_status"],
                has_artifact_gap=has_artifact_gap,
                latest_valuation_job_status=latest_valuation_job_status,
            ),
        )

    def _build_support_job_record(
        self,
        *,
        job_id: int,
        job_type: str,
        business_date: date,
        status: str,
        security_id: str | None,
        epoch: int | None,
        attempt_count: int | None,
        correlation_id: str | None,
        created_at: datetime | None,
        updated_at: datetime | None,
        failure_reason: str | None,
        reference_now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> SupportJobRecord:
        return SupportJobRecord(
            job_id=job_id,
            job_type=job_type,
            business_date=business_date,
            status=status,
            security_id=security_id,
            epoch=epoch,
            attempt_count=attempt_count,
            is_retrying=self._is_support_job_retrying(status, attempt_count),
            correlation_id=correlation_id,
            created_at=created_at,
            updated_at=updated_at,
            is_stale_processing=self._is_support_job_stale(
                status,
                updated_at,
                reference_now,
                stale_threshold_minutes,
            ),
            failure_reason=failure_reason,
            is_terminal_failure=status == "FAILED",
            operational_state=self._get_support_job_operational_state(
                status,
                updated_at,
                reference_now,
                stale_threshold_minutes,
            ),
        )

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.repo.portfolio_exists(portfolio_id):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

    async def get_support_overview(
        self,
        portfolio_id: str,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        failed_window_hours: int = DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    ) -> SupportOverviewResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        (
            latest_business_date,
            current_epoch,
            reprocessing_health,
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
            self.repo.get_reprocessing_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                reference_now=generated_at_utc,
            ),
            self.repo.get_valuation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
            ),
            self.repo.get_analytics_export_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
            ),
            self.repo.get_latest_transaction_date(portfolio_id),
            self.repo.get_latest_snapshot_date_for_current_epoch(portfolio_id),
            self.repo.get_position_snapshot_history_mismatch_count(portfolio_id),
            self.repo.get_latest_financial_reconciliation_control_stage(portfolio_id),
        )
        latest_reconciliation_run = None
        latest_reconciliation_finding_summary: ReconciliationFindingSummary | None = None
        if latest_control_stage is not None:
            latest_reconciliation_run = (
                await self.repo.get_latest_reconciliation_run_for_portfolio_day(
                    portfolio_id=portfolio_id,
                    business_date=latest_control_stage.business_date,
                    epoch=latest_control_stage.epoch,
                )
            )
            if latest_reconciliation_run is not None:
                latest_reconciliation_finding_summary = (
                    await self.repo.get_reconciliation_finding_summary(
                        latest_reconciliation_run.run_id
                    )
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
            reference_date = latest_business_date or generated_at_utc.date()
            valuation_backlog_age_days = max(
                0, (reference_date - valuation_job_health.oldest_open_job_date).days
            )
        aggregation_backlog_age_days = None
        if aggregation_job_health.oldest_open_job_date:
            reference_date = latest_business_date or generated_at_utc.date()
            aggregation_backlog_age_days = max(
                0, (reference_date - aggregation_job_health.oldest_open_job_date).days
            )
        analytics_export_backlog_age_minutes = None
        if analytics_export_job_health.oldest_open_job_created_at:
            delta = (
                generated_at_utc - analytics_export_job_health.oldest_open_job_created_at
            )
            analytics_export_backlog_age_minutes = max(0, int(delta.total_seconds() // 60))
        reprocessing_backlog_age_days = None
        if reprocessing_health.oldest_reprocessing_watermark_date:
            reference_date = latest_business_date or generated_at_utc.date()
            reprocessing_backlog_age_days = max(
                0,
                (
                    reference_date - reprocessing_health.oldest_reprocessing_watermark_date
                ).days,
            )

        controls_status = latest_control_stage.status if latest_control_stage else None
        controls_blocking = self._is_controls_blocking(controls_status)

        return SupportOverviewResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            current_epoch=current_epoch,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            generated_at_utc=generated_at_utc,
            active_reprocessing_keys=reprocessing_health.active_keys,
            stale_reprocessing_keys=reprocessing_health.stale_reprocessing_keys,
            oldest_reprocessing_watermark_date=(
                reprocessing_health.oldest_reprocessing_watermark_date
            ),
            oldest_reprocessing_security_id=reprocessing_health.oldest_reprocessing_security_id,
            oldest_reprocessing_epoch=reprocessing_health.oldest_reprocessing_epoch,
            oldest_reprocessing_updated_at=reprocessing_health.oldest_reprocessing_updated_at,
            reprocessing_backlog_age_days=reprocessing_backlog_age_days,
            pending_valuation_jobs=valuation_job_health.pending_jobs,
            processing_valuation_jobs=valuation_job_health.processing_jobs,
            stale_processing_valuation_jobs=valuation_job_health.stale_processing_jobs,
            failed_valuation_jobs=valuation_job_health.failed_jobs,
            failed_valuation_jobs_within_window=valuation_job_health.failed_jobs_last_hours,
            oldest_pending_valuation_date=valuation_job_health.oldest_open_job_date,
            oldest_pending_valuation_job_id=valuation_job_health.oldest_open_job_id,
            oldest_pending_valuation_security_id=valuation_job_health.oldest_open_security_id,
            oldest_pending_valuation_correlation_id=(
                valuation_job_health.oldest_open_job_correlation_id
            ),
            valuation_backlog_age_days=valuation_backlog_age_days,
            pending_aggregation_jobs=aggregation_job_health.pending_jobs,
            processing_aggregation_jobs=aggregation_job_health.processing_jobs,
            stale_processing_aggregation_jobs=aggregation_job_health.stale_processing_jobs,
            failed_aggregation_jobs=aggregation_job_health.failed_jobs,
            failed_aggregation_jobs_within_window=aggregation_job_health.failed_jobs_last_hours,
            oldest_pending_aggregation_date=aggregation_job_health.oldest_open_job_date,
            oldest_pending_aggregation_job_id=aggregation_job_health.oldest_open_job_id,
            oldest_pending_aggregation_correlation_id=(
                aggregation_job_health.oldest_open_job_correlation_id
            ),
            aggregation_backlog_age_days=aggregation_backlog_age_days,
            pending_analytics_export_jobs=analytics_export_job_health.accepted_jobs,
            processing_analytics_export_jobs=analytics_export_job_health.running_jobs,
            stale_processing_analytics_export_jobs=analytics_export_job_health.stale_running_jobs,
            failed_analytics_export_jobs=analytics_export_job_health.failed_jobs,
            failed_analytics_export_jobs_within_window=(
                analytics_export_job_health.failed_jobs_last_hours
            ),
            oldest_pending_analytics_export_created_at=(
                analytics_export_job_health.oldest_open_job_created_at
            ),
            oldest_pending_analytics_export_job_id=(
                analytics_export_job_health.oldest_open_job_id
            ),
            oldest_pending_analytics_export_request_fingerprint=(
                analytics_export_job_health.oldest_open_request_fingerprint
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
            controls_stage_id=(latest_control_stage.id if latest_control_stage else None),
            controls_last_source_event_type=(
                latest_control_stage.last_source_event_type if latest_control_stage else None
            ),
            controls_created_at=(
                latest_control_stage.created_at if latest_control_stage else None
            ),
            controls_ready_emitted_at=(
                latest_control_stage.ready_emitted_at if latest_control_stage else None
            ),
            controls_epoch=latest_control_stage.epoch if latest_control_stage else None,
            controls_status=controls_status,
            controls_failure_reason=(
                latest_control_stage.failure_reason if latest_control_stage else None
            ),
            controls_latest_reconciliation_run_id=(
                latest_reconciliation_run.run_id if latest_reconciliation_run else None
            ),
            controls_latest_reconciliation_type=(
                latest_reconciliation_run.reconciliation_type
                if latest_reconciliation_run
                else None
            ),
            controls_latest_reconciliation_status=(
                latest_reconciliation_run.status if latest_reconciliation_run else None
            ),
            controls_latest_reconciliation_correlation_id=(
                latest_reconciliation_run.correlation_id
                if latest_reconciliation_run
                else None
            ),
            controls_latest_reconciliation_requested_by=(
                latest_reconciliation_run.requested_by
                if latest_reconciliation_run
                else None
            ),
            controls_latest_reconciliation_dedupe_key=(
                latest_reconciliation_run.dedupe_key
                if latest_reconciliation_run
                else None
            ),
            controls_latest_reconciliation_failure_reason=(
                latest_reconciliation_run.failure_reason
                if latest_reconciliation_run
                else None
            ),
            controls_latest_reconciliation_total_findings=(
                latest_reconciliation_finding_summary.total_findings
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_latest_reconciliation_blocking_findings=(
                latest_reconciliation_finding_summary.blocking_findings
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_latest_blocking_finding_id=(
                latest_reconciliation_finding_summary.top_blocking_finding_id
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_latest_blocking_finding_type=(
                latest_reconciliation_finding_summary.top_blocking_finding_type
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_latest_blocking_finding_security_id=(
                latest_reconciliation_finding_summary.top_blocking_finding_security_id
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_latest_blocking_finding_transaction_id=(
                latest_reconciliation_finding_summary.top_blocking_finding_transaction_id
                if latest_reconciliation_finding_summary
                else None
            ),
            controls_last_updated_at=(
                latest_control_stage.updated_at if latest_control_stage else None
            ),
            controls_blocking=controls_blocking,
            publish_allowed=not controls_blocking,
        )

    @staticmethod
    def _is_controls_blocking(status: str | None) -> bool:
        return status in {"FAILED", "REQUIRES_REPLAY"}

    async def get_calculator_slos(
        self,
        portfolio_id: str,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        failed_window_hours: int = DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    ) -> CalculatorSloResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        (
            latest_business_date,
            reprocessing_health,
            valuation_job_health,
            aggregation_job_health,
        ) = await asyncio.gather(
            self.repo.get_latest_business_date(),
            self.repo.get_reprocessing_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                reference_now=generated_at_utc,
            ),
            self.repo.get_valuation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
            ),
        )

        reference_date = latest_business_date or generated_at_utc.date()
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
        reprocessing_backlog_age_days = (
            max(0, (reference_date - reprocessing_health.oldest_reprocessing_watermark_date).days)
            if reprocessing_health.oldest_reprocessing_watermark_date is not None
            else None
        )

        return CalculatorSloResponse(
            portfolio_id=portfolio_id,
            business_date=latest_business_date,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            generated_at_utc=generated_at_utc,
            valuation=CalculatorSloBucket(
                pending_jobs=valuation_job_health.pending_jobs,
                processing_jobs=valuation_job_health.processing_jobs,
                stale_processing_jobs=valuation_job_health.stale_processing_jobs,
                failed_jobs=valuation_job_health.failed_jobs,
                failed_jobs_within_window=valuation_job_health.failed_jobs_last_hours,
                oldest_open_job_date=valuation_job_health.oldest_open_job_date,
                oldest_open_job_id=valuation_job_health.oldest_open_job_id,
                oldest_open_job_correlation_id=(
                    valuation_job_health.oldest_open_job_correlation_id
                ),
                backlog_age_days=valuation_backlog_age_days,
            ),
            aggregation=CalculatorSloBucket(
                pending_jobs=aggregation_job_health.pending_jobs,
                processing_jobs=aggregation_job_health.processing_jobs,
                stale_processing_jobs=aggregation_job_health.stale_processing_jobs,
                failed_jobs=aggregation_job_health.failed_jobs,
                failed_jobs_within_window=aggregation_job_health.failed_jobs_last_hours,
                oldest_open_job_date=aggregation_job_health.oldest_open_job_date,
                oldest_open_job_id=aggregation_job_health.oldest_open_job_id,
                oldest_open_job_correlation_id=(
                    aggregation_job_health.oldest_open_job_correlation_id
                ),
                backlog_age_days=aggregation_backlog_age_days,
            ),
            reprocessing=ReprocessingSloBucket(
                active_reprocessing_keys=reprocessing_health.active_keys,
                stale_reprocessing_keys=reprocessing_health.stale_reprocessing_keys,
                oldest_reprocessing_watermark_date=(
                    reprocessing_health.oldest_reprocessing_watermark_date
                ),
                oldest_reprocessing_security_id=(
                    reprocessing_health.oldest_reprocessing_security_id
                ),
                oldest_reprocessing_epoch=reprocessing_health.oldest_reprocessing_epoch,
                oldest_reprocessing_updated_at=(
                    reprocessing_health.oldest_reprocessing_updated_at
                ),
                backlog_age_days=reprocessing_backlog_age_days,
            ),
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

        latest_valuation_job_date = (
            latest_valuation_job.valuation_date if latest_valuation_job else None
        )
        latest_valuation_job_status = (
            latest_valuation_job.status if latest_valuation_job else None
        )
        has_artifact_gap = self._has_lineage_artifact_gap(
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        return LineageResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=position_state.epoch,
            watermark_date=position_state.watermark_date,
            reprocessing_status=position_state.status,
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_id=(latest_valuation_job.id if latest_valuation_job else None),
            latest_valuation_job_status=latest_valuation_job_status,
            latest_valuation_job_correlation_id=(
                latest_valuation_job.correlation_id if latest_valuation_job else None
            ),
            has_artifact_gap=has_artifact_gap,
            operational_state=self._get_lineage_key_operational_state(
                reprocessing_status=position_state.status,
                has_artifact_gap=has_artifact_gap,
                latest_valuation_job_status=latest_valuation_job_status,
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
            items=[self._build_lineage_key_record(k) for k in keys],
        )

    async def get_valuation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        business_date: date | None = None,
        security_id: str | None = None,
        job_id: int | None = None,
        correlation_id: str | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        total, jobs = await asyncio.gather(
            self.repo.get_valuation_jobs_count(
                portfolio_id=portfolio_id,
                status=status,
                business_date=business_date,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
            ),
            self.repo.get_valuation_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=status,
                business_date=business_date,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                self._build_support_job_record(
                    job_id=job.id,
                    job_type="VALUATION",
                    business_date=job.valuation_date,
                    status=job.status,
                    security_id=job.security_id,
                    epoch=job.epoch,
                    attempt_count=job.attempt_count,
                    correlation_id=job.correlation_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    failure_reason=job.failure_reason,
                    reference_now=generated_at_utc,
                    stale_threshold_minutes=stale_threshold_minutes,
                )
                for job in jobs
            ],
        )

    async def get_aggregation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        business_date: date | None = None,
        job_id: int | None = None,
        correlation_id: str | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        total, jobs = await asyncio.gather(
            self.repo.get_aggregation_jobs_count(
                portfolio_id=portfolio_id,
                status=status,
                business_date=business_date,
                job_id=job_id,
                correlation_id=correlation_id,
            ),
            self.repo.get_aggregation_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=status,
                business_date=business_date,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                self._build_support_job_record(
                    job_id=job.id,
                    job_type="AGGREGATION",
                    business_date=job.aggregation_date,
                    status=job.status,
                    security_id=None,
                    epoch=None,
                    attempt_count=job.attempt_count,
                    correlation_id=job.correlation_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    failure_reason=job.failure_reason,
                    reference_now=generated_at_utc,
                    stale_threshold_minutes=stale_threshold_minutes,
                )
                for job in jobs
            ],
        )

    async def get_analytics_export_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        job_id: str | None = None,
        request_fingerprint: str | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> AnalyticsExportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        total, jobs = await asyncio.gather(
            self.repo.get_analytics_export_jobs_count(
                portfolio_id=portfolio_id,
                status=status,
                job_id=job_id,
                request_fingerprint=request_fingerprint,
            ),
            self.repo.get_analytics_export_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=status,
                job_id=job_id,
                request_fingerprint=request_fingerprint,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
            ),
        )
        return AnalyticsExportJobListResponse(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                AnalyticsExportJobRecord(
                    job_id=job.job_id,
                    request_fingerprint=job.request_fingerprint,
                    dataset_type=job.dataset_type,
                    status=job.status,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    updated_at=job.updated_at,
                    is_stale_running=self._is_analytics_export_job_stale(
                        job.status,
                        job.updated_at,
                        generated_at_utc,
                        stale_threshold_minutes,
                    ),
                    backlog_age_minutes=self._get_analytics_export_backlog_age_minutes(
                        job.status, job.created_at, generated_at_utc
                    ),
                    result_row_count=job.result_row_count,
                    error_message=job.error_message,
                    is_terminal_failure=(
                        self._normalize_analytics_export_status(job.status) == "failed"
                    ),
                    operational_state=self._get_analytics_export_operational_state(
                        job.status,
                        job.updated_at,
                        generated_at_utc,
                        stale_threshold_minutes,
                    ),
                )
                for job in jobs
            ],
        )

    async def get_reconciliation_runs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        run_id: str | None = None,
        correlation_id: str | None = None,
        reconciliation_type: str | None = None,
        status: str | None = None,
    ) -> ReconciliationRunListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, runs = await asyncio.gather(
            self.repo.get_reconciliation_runs_count(
                portfolio_id=portfolio_id,
                run_id=run_id,
                correlation_id=correlation_id,
                reconciliation_type=reconciliation_type,
                status=status,
            ),
            self.repo.get_reconciliation_runs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                run_id=run_id,
                correlation_id=correlation_id,
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
                    requested_by=run.requested_by,
                    dedupe_key=run.dedupe_key,
                    correlation_id=run.correlation_id,
                    failure_reason=run.failure_reason,
                    is_terminal_failure=run.status == "FAILED",
                    is_blocking=self._is_controls_blocking(run.status),
                    operational_state=self._get_reconciliation_operational_state(run.status),
                )
                for run in runs
            ],
        )

    async def get_reconciliation_findings(
        self,
        portfolio_id: str,
        run_id: str,
        limit: int,
        finding_id: str | None = None,
        security_id: str | None = None,
        transaction_id: str | None = None,
    ) -> ReconciliationFindingListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        run = await self.repo.get_reconciliation_run(portfolio_id=portfolio_id, run_id=run_id)
        if run is None:
            raise ValueError(f"Reconciliation run {run_id} not found for portfolio {portfolio_id}")
        total, findings = await asyncio.gather(
            self.repo.get_reconciliation_findings_count(
                run_id=run_id,
                finding_id=finding_id,
                security_id=security_id,
                transaction_id=transaction_id,
            ),
            self.repo.get_reconciliation_findings(
                run_id=run_id,
                limit=limit,
                finding_id=finding_id,
                security_id=security_id,
                transaction_id=transaction_id,
            ),
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
                    is_blocking=self._is_reconciliation_finding_blocking(finding.severity),
                    operational_state=self._get_reconciliation_finding_operational_state(
                        finding.severity
                    ),
                )
                for finding in findings
            ],
        )

    async def get_portfolio_control_stages(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        stage_id: int | None = None,
        stage_name: str | None = None,
        business_date: date | None = None,
        status: str | None = None,
    ) -> PortfolioControlStageListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        total, stages = await asyncio.gather(
            self.repo.get_portfolio_control_stages_count(
                portfolio_id=portfolio_id,
                stage_id=stage_id,
                stage_name=stage_name,
                business_date=business_date,
                status=status,
            ),
            self.repo.get_portfolio_control_stages(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                stage_id=stage_id,
                stage_name=stage_name,
                business_date=business_date,
                status=status,
            ),
        )
        return PortfolioControlStageListResponse(
            portfolio_id=portfolio_id,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                PortfolioControlStageRecord(
                    stage_id=stage.id,
                    stage_name=stage.stage_name,
                    business_date=stage.business_date,
                    epoch=stage.epoch,
                    status=stage.status,
                    last_source_event_type=stage.last_source_event_type,
                    created_at=stage.created_at,
                    ready_emitted_at=stage.ready_emitted_at,
                    updated_at=stage.updated_at,
                    is_blocking=self._is_controls_blocking(stage.status),
                    operational_state=self._get_portfolio_control_stage_operational_state(
                        stage.status
                    ),
                )
                for stage in stages
            ],
        )

    async def get_reprocessing_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        security_id: str | None = None,
        watermark_date: date | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> ReprocessingKeyListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        total, keys = await asyncio.gather(
            self.repo.get_reprocessing_keys_count(
                portfolio_id=portfolio_id,
                status=status,
                security_id=security_id,
                watermark_date=watermark_date,
            ),
            self.repo.get_reprocessing_keys(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=status,
                security_id=security_id,
                watermark_date=watermark_date,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
            ),
        )
        return ReprocessingKeyListResponse(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                ReprocessingKeyRecord(
                    security_id=key.security_id,
                    epoch=key.epoch,
                    watermark_date=key.watermark_date,
                    status=key.status,
                    created_at=key.created_at,
                    updated_at=key.updated_at,
                    is_stale_reprocessing=self._is_reprocessing_key_stale(
                        key.status,
                        key.updated_at,
                        generated_at_utc,
                        stale_threshold_minutes,
                    ),
                    operational_state=self._get_reprocessing_key_operational_state(
                        key.status,
                        key.updated_at,
                        generated_at_utc,
                        stale_threshold_minutes,
                    ),
                )
                for key in keys
            ],
        )

    async def get_reprocessing_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        security_id: str | None = None,
        job_id: int | None = None,
        correlation_id: str | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> SupportJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        total, jobs = await asyncio.gather(
            self.repo.get_reprocessing_jobs_count(
                portfolio_id=portfolio_id,
                status=status,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
            ),
            self.repo.get_reprocessing_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=status,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
            ),
        )
        return SupportJobListResponse(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                self._build_support_job_record(
                    job_id=job.id,
                    job_type=job.job_type,
                    business_date=date.fromisoformat(job.business_date),
                    status=job.status,
                    security_id=job.security_id,
                    epoch=None,
                    attempt_count=job.attempt_count,
                    correlation_id=job.correlation_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    failure_reason=job.failure_reason,
                    reference_now=generated_at_utc,
                    stale_threshold_minutes=stale_threshold_minutes,
                )
                for job in jobs
            ],
        )

    @classmethod
    def _is_support_job_stale(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> bool:
        if status != "PROCESSING" or updated_at is None:
            return False
        reference_now = now or datetime.now(timezone.utc)
        return updated_at < reference_now - timedelta(minutes=stale_threshold_minutes)

    @classmethod
    def _is_analytics_export_job_stale(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> bool:
        normalized_status = cls._normalize_analytics_export_status(status)
        normalized_status = "PROCESSING" if normalized_status == "running" else normalized_status
        return cls._is_support_job_stale(
            normalized_status,
            updated_at,
            now,
            stale_threshold_minutes,
        )

    @classmethod
    def _is_reprocessing_key_stale(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> bool:
        normalized_status = "PROCESSING" if status == "REPROCESSING" else status
        return cls._is_support_job_stale(
            normalized_status,
            updated_at,
            now,
            stale_threshold_minutes,
        )

    @staticmethod
    def _get_analytics_export_backlog_age_minutes(
        status: str | None, created_at: datetime | None, now: datetime | None = None
    ) -> int | None:
        normalized_status = OperationsService._normalize_analytics_export_status(status)
        if normalized_status not in {"accepted", "running"} or created_at is None:
            return None
        reference_now = now or datetime.now(timezone.utc)
        return max(0, int((reference_now - created_at).total_seconds() // 60))
