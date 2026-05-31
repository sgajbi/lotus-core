import asyncio
from collections.abc import Awaitable
from datetime import date, datetime, timedelta, timezone
from typing import TypeVar

from portfolio_common.reconciliation_quality import (
    BLOCKED,
    BREAK_OPEN,
    COMPLETE,
    PARTIAL,
    UNKNOWN,
    ReconciliationRunSignal,
    classify_finding_status,
    classify_reconciliation_status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import (
    AnalyticsExportJobListResponse,
    AnalyticsExportJobRecord,
    CalculatorSloResponse,
    LineageKeyListResponse,
    LineageKeyRecord,
    LineageResponse,
    LoadRunProgressResponse,
    PortfolioControlStageListResponse,
    PortfolioControlStageRecord,
    PortfolioReadinessResponse,
    ReconciliationFindingListResponse,
    ReconciliationFindingRecord,
    ReconciliationRunListResponse,
    ReconciliationRunRecord,
    ReprocessingJobListResponse,
    ReprocessingKeyListResponse,
    ReprocessingKeyRecord,
    SupportJobListResponse,
    SupportJobRecord,
    SupportOverviewResponse,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.operations_models import (
    MissingHistoricalFxDependencySummary,
    SnapshotValuationCoverageSummary,
)
from ..repositories.operations_repository import OperationsRepository
from ..support_policy import (
    DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
)
from .calculator_slo_builder import build_calculator_slo_response
from .load_run_progress_builder import build_load_run_progress_response
from .portfolio_readiness_builder import (
    PortfolioReadinessSnapshot,
    build_portfolio_readiness_response,
)
from .support_overview_builder import (
    SupportOverviewSnapshot,
    build_support_overview_response,
)

_PagedRowT = TypeVar("_PagedRowT")


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.repo = OperationsRepository(db)

    @staticmethod
    def _evidence_product_runtime_metadata(
        *,
        generated_at_utc: datetime,
        as_of_dates: list[date | None],
        evidence_timestamps: list[datetime | None],
        reconciliation_status: str = UNKNOWN,
    ) -> dict[str, object]:
        resolved_as_of_dates = [as_of_date for as_of_date in as_of_dates if as_of_date is not None]
        resolved_timestamps = [
            evidence_timestamp
            for evidence_timestamp in evidence_timestamps
            if evidence_timestamp is not None
        ]
        return source_data_product_runtime_metadata(
            as_of_date=(
                max(resolved_as_of_dates) if resolved_as_of_dates else generated_at_utc.date()
            ),
            generated_at=generated_at_utc,
            reconciliation_status=reconciliation_status,
            latest_evidence_timestamp=(max(resolved_timestamps) if resolved_timestamps else None),
        )

    @staticmethod
    def _aggregate_reconciliation_run_status(runs: list[object]) -> str:
        statuses = [
            classify_reconciliation_status(
                ReconciliationRunSignal(
                    run_status=getattr(run, "status", None),
                    has_run=True,
                )
            )
            for run in runs
        ]
        return OperationsService._aggregate_statuses(statuses)

    @staticmethod
    def _aggregate_reconciliation_finding_status(findings: list[object], total: int) -> str:
        if not findings:
            return COMPLETE if total == 0 else UNKNOWN
        statuses = [
            classify_finding_status(severity=str(getattr(finding, "severity", "")))
            for finding in findings
        ]
        return OperationsService._aggregate_statuses(statuses)

    @staticmethod
    def _aggregate_statuses(statuses: list[str]) -> str:
        if not statuses:
            return UNKNOWN
        if BLOCKED in statuses:
            return BLOCKED
        if BREAK_OPEN in statuses:
            return BREAK_OPEN
        if PARTIAL in statuses:
            return PARTIAL
        if all(status == COMPLETE for status in statuses):
            return COMPLETE
        return UNKNOWN

    @staticmethod
    def _normalize_support_job_status(status: str | None) -> str | None:
        if status is None:
            return None
        return status.strip().upper()

    @classmethod
    def _normalize_support_status_filter(cls, status: str | None) -> str | None:
        normalized_status = cls._normalize_support_job_status(status)
        return normalized_status or None

    @classmethod
    def _get_support_job_operational_state(
        cls,
        status: str,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        normalized_status = cls._normalize_support_job_status(status) or ""
        if normalized_status == "FAILED":
            return "FAILED"
        if normalized_status.startswith("SKIPPED"):
            return "SKIPPED"
        if cls._is_support_job_stale(normalized_status, updated_at, now, stale_threshold_minutes):
            return "STALE_PROCESSING"
        if normalized_status == "PROCESSING":
            return "PROCESSING"
        if normalized_status == "PENDING":
            return "PENDING"
        return "COMPLETED"

    @classmethod
    def _is_terminal_failure_status(cls, status: str | None) -> bool:
        return cls._normalize_support_job_status(status) == "FAILED"

    @classmethod
    def _is_support_job_retrying(cls, status: str, attempt_count: int | None) -> bool:
        normalized_status = cls._normalize_support_job_status(status)
        return (attempt_count or 0) > 0 and normalized_status in {"PENDING", "PROCESSING"}

    @staticmethod
    def _normalize_analytics_export_status(status: str | None) -> str | None:
        if status is None:
            return None
        return status.strip().lower()

    @classmethod
    def _normalize_analytics_export_status_filter(cls, status: str | None) -> str | None:
        normalized_status = cls._normalize_analytics_export_status(status)
        return normalized_status or None

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
        if cls._is_analytics_export_job_stale(status, updated_at, now, stale_threshold_minutes):
            return "STALE_RUNNING"
        if status == "running":
            return "RUNNING"
        if status == "accepted":
            return "ACCEPTED"
        return "COMPLETED"

    @classmethod
    def _get_reconciliation_operational_state(cls, status: str | None) -> str:
        normalized_status = cls._normalize_support_job_status(status)
        if cls._is_controls_blocking(status):
            return "BLOCKING"
        if normalized_status == "RUNNING":
            return "RUNNING"
        return "COMPLETED"

    @classmethod
    def _get_portfolio_control_stage_operational_state(cls, status: str | None) -> str:
        return "BLOCKING" if cls._is_controls_blocking(status) else "COMPLETED"

    @classmethod
    def _is_reconciliation_finding_blocking(cls, severity: str | None) -> bool:
        return cls._normalize_support_job_status(severity) == "ERROR"

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
        normalized_status = cls._normalize_support_job_status(status)
        if cls._is_reprocessing_key_stale(status, updated_at, now, stale_threshold_minutes):
            return "STALE_REPROCESSING"
        if normalized_status == "REPROCESSING":
            return "REPROCESSING"
        return "CURRENT"

    @classmethod
    def _has_lineage_artifact_gap(
        cls,
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
        normalized_status = cls._normalize_support_job_status(latest_valuation_job_status)
        return normalized_status in {"FAILED", "PENDING", "PROCESSING"}

    @classmethod
    def _get_lineage_key_operational_state(
        cls,
        reprocessing_status: str | None,
        has_artifact_gap: bool,
        latest_valuation_job_status: str | None,
    ) -> str:
        normalized_reprocessing_status = cls._normalize_support_job_status(reprocessing_status)
        normalized_valuation_status = cls._normalize_support_job_status(latest_valuation_job_status)
        if normalized_reprocessing_status == "REPROCESSING":
            return "REPLAYING"
        if has_artifact_gap:
            if normalized_valuation_status == "FAILED":
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
            security_id=normalize_security_id(key["security_id"]),
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
            security_id=normalize_security_id(security_id) if security_id is not None else None,
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
            is_terminal_failure=self._is_terminal_failure_status(status),
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

    async def _resolve_portfolio_latest_business_date(
        self,
        portfolio_id: str,
        *,
        generated_at_utc: datetime,
    ) -> date | None:
        portfolio_exists, latest_business_date = await asyncio.gather(
            self.repo.portfolio_exists(portfolio_id),
            self.repo.get_latest_business_date(as_of=generated_at_utc),
        )
        if not portfolio_exists:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")
        return latest_business_date

    async def _read_count_and_page(
        self,
        count_read: Awaitable[int],
        page_read: Awaitable[list[_PagedRowT]],
    ) -> tuple[int, list[_PagedRowT]]:
        total, rows = await asyncio.gather(count_read, page_read)
        return total, rows

    async def get_load_run_progress(
        self,
        run_id: str,
        business_date: date,
    ) -> LoadRunProgressResponse:
        generated_at_utc = datetime.now(timezone.utc)
        summary = await self.repo.get_load_run_progress(
            run_id=run_id,
            business_date=business_date,
            as_of=generated_at_utc,
        )
        if summary.portfolios_ingested == 0 and summary.transactions_ingested == 0:
            raise ValueError(f"Load run {run_id} not found")
        return build_load_run_progress_response(
            run_id=run_id,
            business_date=business_date,
            generated_at_utc=generated_at_utc,
            summary=summary,
        )

    async def get_support_overview(
        self,
        portfolio_id: str,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        failed_window_hours: int = DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    ) -> SupportOverviewResponse:
        generated_at_utc = datetime.now(timezone.utc)
        latest_business_date = await self._resolve_portfolio_latest_business_date(
            portfolio_id,
            generated_at_utc=generated_at_utc,
        )
        (
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
            self.repo.get_current_portfolio_epoch(portfolio_id, as_of=generated_at_utc),
            self.repo.get_reprocessing_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_valuation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_analytics_export_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_latest_transaction_date(portfolio_id, as_of=generated_at_utc),
            self.repo.get_latest_snapshot_date_for_current_epoch(
                portfolio_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_position_snapshot_history_mismatch_count(
                portfolio_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_latest_financial_reconciliation_control_stage(
                portfolio_id,
                as_of=generated_at_utc,
            ),
        )
        latest_reconciliation_run = None
        latest_reconciliation_finding_summary = None
        if latest_control_stage is not None:
            latest_reconciliation_run = (
                await self.repo.get_latest_reconciliation_run_for_portfolio_day(
                    portfolio_id=portfolio_id,
                    business_date=latest_control_stage.business_date,
                    epoch=latest_control_stage.epoch,
                    as_of=latest_control_stage.updated_at,
                )
            )
            if latest_reconciliation_run is not None:
                latest_reconciliation_finding_summary = (
                    await self.repo.get_reconciliation_finding_summary(
                        latest_reconciliation_run.run_id,
                        as_of=latest_control_stage.updated_at,
                    )
                )

        latest_booked_transaction_date = None
        latest_booked_position_snapshot_date = None
        if latest_business_date is not None:
            (
                latest_booked_transaction_date,
                latest_booked_position_snapshot_date,
            ) = await asyncio.gather(
                self.repo.get_latest_transaction_date_as_of(
                    portfolio_id,
                    latest_business_date,
                    snapshot_as_of=generated_at_utc,
                ),
                self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                    portfolio_id,
                    latest_business_date,
                    snapshot_as_of=generated_at_utc,
                ),
            )

        controls_status = latest_control_stage.status if latest_control_stage else None
        controls_blocking = self._is_controls_blocking(controls_status)

        return build_support_overview_response(
            SupportOverviewSnapshot(
                portfolio_id=portfolio_id,
                latest_business_date=latest_business_date,
                current_epoch=current_epoch,
                stale_threshold_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                generated_at_utc=generated_at_utc,
                reprocessing_health=reprocessing_health,
                valuation_job_health=valuation_job_health,
                aggregation_job_health=aggregation_job_health,
                analytics_export_job_health=analytics_export_job_health,
                latest_transaction_date=latest_transaction_date,
                latest_booked_transaction_date=latest_booked_transaction_date,
                latest_position_snapshot_date=latest_position_snapshot_date_unbounded,
                latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
                position_snapshot_history_mismatch_count=position_snapshot_history_mismatch_count,
                latest_control_stage=latest_control_stage,
                latest_reconciliation_run=latest_reconciliation_run,
                latest_reconciliation_finding_summary=latest_reconciliation_finding_summary,
                controls_blocking=controls_blocking,
            )
        )

    async def get_portfolio_readiness(
        self,
        portfolio_id: str,
        as_of_date: date | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        failed_window_hours: int = DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    ) -> PortfolioReadinessResponse:
        support_overview = await self.get_support_overview(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
        )
        generated_at_utc = support_overview.generated_at_utc
        resolved_as_of_date = (
            as_of_date
            or support_overview.business_date
            or support_overview.latest_position_snapshot_date
            or support_overview.latest_transaction_date
        )

        if resolved_as_of_date is None:
            latest_booked_transaction_date = None
            latest_booked_position_snapshot_date = None
            snapshot_coverage = SnapshotValuationCoverageSummary(
                snapshot_date=None,
                total_positions=0,
                valued_positions=0,
                unvalued_positions=0,
            )
            missing_fx_summary = MissingHistoricalFxDependencySummary(
                missing_count=0,
                earliest_transaction_date=None,
                latest_transaction_date=None,
                sample_records=[],
            )
        else:
            snapshot_coverage_date = (
                support_overview.latest_booked_position_snapshot_date
                if as_of_date is None
                else resolved_as_of_date
            )
            (
                latest_booked_transaction_date,
                latest_booked_position_snapshot_date,
                missing_fx_summary,
            ) = await asyncio.gather(
                self.repo.get_latest_transaction_date_as_of(
                    portfolio_id,
                    resolved_as_of_date,
                    snapshot_as_of=generated_at_utc,
                ),
                self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                    portfolio_id,
                    resolved_as_of_date,
                    snapshot_as_of=generated_at_utc,
                ),
                self.repo.get_missing_historical_fx_dependency_summary(
                    portfolio_id,
                    resolved_as_of_date,
                    snapshot_as_of=generated_at_utc,
                ),
            )
            snapshot_coverage = await self.repo.get_snapshot_valuation_coverage_summary(
                portfolio_id,
                latest_booked_position_snapshot_date
                if latest_booked_position_snapshot_date is not None
                else snapshot_coverage_date,
                snapshot_as_of=generated_at_utc,
            )

        return build_portfolio_readiness_response(
            PortfolioReadinessSnapshot(
                portfolio_id=portfolio_id,
                requested_as_of_date=as_of_date,
                resolved_as_of_date=resolved_as_of_date,
                generated_at_utc=generated_at_utc,
                support_overview=support_overview,
                latest_booked_transaction_date=latest_booked_transaction_date,
                latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
                snapshot_coverage=snapshot_coverage,
                missing_fx_summary=missing_fx_summary,
            )
        )

    @classmethod
    def _is_controls_blocking(cls, status: str | None) -> bool:
        normalized_status = cls._normalize_support_job_status(status)
        return normalized_status in {"FAILED", "REQUIRES_REPLAY"}

    async def get_calculator_slos(
        self,
        portfolio_id: str,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        failed_window_hours: int = DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    ) -> CalculatorSloResponse:
        generated_at_utc = datetime.now(timezone.utc)
        latest_business_date = await self._resolve_portfolio_latest_business_date(
            portfolio_id,
            generated_at_utc=generated_at_utc,
        )
        (
            reprocessing_health,
            valuation_job_health,
            aggregation_job_health,
        ) = await asyncio.gather(
            self.repo.get_reprocessing_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_valuation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
            self.repo.get_aggregation_job_health_summary(
                portfolio_id,
                stale_minutes=stale_threshold_minutes,
                failed_window_hours=failed_window_hours,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
        )

        return build_calculator_slo_response(
            portfolio_id=portfolio_id,
            latest_business_date=latest_business_date,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            generated_at_utc=generated_at_utc,
            reprocessing_health=reprocessing_health,
            valuation_job_health=valuation_job_health,
            aggregation_job_health=aggregation_job_health,
        )

    async def get_lineage(self, portfolio_id: str, security_id: str) -> LineageResponse:
        generated_at_utc = datetime.now(timezone.utc)
        position_state = await self.repo.get_position_state(
            portfolio_id,
            security_id,
            as_of=generated_at_utc,
        )
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
                portfolio_id,
                security_id,
                position_state.epoch,
                as_of=generated_at_utc,
            ),
            self.repo.get_latest_daily_snapshot_date(
                portfolio_id,
                security_id,
                position_state.epoch,
                as_of=generated_at_utc,
            ),
            self.repo.get_latest_valuation_job(
                portfolio_id,
                security_id,
                position_state.epoch,
                as_of=generated_at_utc,
            ),
        )

        latest_valuation_job_date = (
            latest_valuation_job.valuation_date if latest_valuation_job else None
        )
        latest_valuation_job_status = latest_valuation_job.status if latest_valuation_job else None
        has_artifact_gap = self._has_lineage_artifact_gap(
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=latest_valuation_job_date,
            latest_valuation_job_status=latest_valuation_job_status,
        )
        return LineageResponse(
            generated_at_utc=generated_at_utc,
            portfolio_id=portfolio_id,
            security_id=normalize_security_id(security_id),
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
        generated_at_utc = datetime.now(timezone.utc)
        normalized_reprocessing_status = self._normalize_support_status_filter(reprocessing_status)
        total, keys = await self._read_count_and_page(
            self.repo.get_lineage_keys_count(
                portfolio_id=portfolio_id,
                reprocessing_status=normalized_reprocessing_status,
                security_id=security_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_lineage_keys(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                reprocessing_status=normalized_reprocessing_status,
                security_id=security_id,
                as_of=generated_at_utc,
            ),
        )
        return LineageKeyListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[
                    evidence_date
                    for key in keys
                    for evidence_date in (
                        key.get("latest_position_history_date"),
                        key.get("latest_daily_snapshot_date"),
                        key.get("latest_valuation_job_date"),
                        key.get("watermark_date"),
                    )
                ],
                evidence_timestamps=[],
            ),
            generated_at_utc=generated_at_utc,
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
        normalized_status = self._normalize_support_status_filter(status)
        total, jobs = await self._read_count_and_page(
            self.repo.get_valuation_jobs_count(
                portfolio_id=portfolio_id,
                status=normalized_status,
                business_date=business_date,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_valuation_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=normalized_status,
                business_date=business_date,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
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
        normalized_status = self._normalize_support_status_filter(status)
        total, jobs = await self._read_count_and_page(
            self.repo.get_aggregation_jobs_count(
                portfolio_id=portfolio_id,
                status=normalized_status,
                business_date=business_date,
                job_id=job_id,
                correlation_id=correlation_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_aggregation_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=normalized_status,
                business_date=business_date,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
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
        normalized_status = self._normalize_analytics_export_status_filter(status)
        total, jobs = await self._read_count_and_page(
            self.repo.get_analytics_export_jobs_count(
                portfolio_id=portfolio_id,
                status=normalized_status,
                job_id=job_id,
                request_fingerprint=request_fingerprint,
                as_of=generated_at_utc,
            ),
            self.repo.get_analytics_export_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=normalized_status,
                job_id=job_id,
                request_fingerprint=request_fingerprint,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
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
        requested_by: str | None = None,
        dedupe_key: str | None = None,
        reconciliation_type: str | None = None,
        status: str | None = None,
    ) -> ReconciliationRunListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        normalized_status = self._normalize_support_status_filter(status)
        total, runs = await self._read_count_and_page(
            self.repo.get_reconciliation_runs_count(
                portfolio_id=portfolio_id,
                run_id=run_id,
                correlation_id=correlation_id,
                requested_by=requested_by,
                dedupe_key=dedupe_key,
                reconciliation_type=reconciliation_type,
                status=normalized_status,
                as_of=generated_at_utc,
            ),
            self.repo.get_reconciliation_runs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                run_id=run_id,
                correlation_id=correlation_id,
                requested_by=requested_by,
                dedupe_key=dedupe_key,
                reconciliation_type=reconciliation_type,
                status=normalized_status,
                as_of=generated_at_utc,
            ),
        )
        return ReconciliationRunListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[
                    run.business_date
                    or (run.completed_at.date() if run.completed_at is not None else None)
                    or run.started_at.date()
                    for run in runs
                ],
                evidence_timestamps=[run.completed_at or run.started_at for run in runs],
                reconciliation_status=self._aggregate_reconciliation_run_status(runs),
            ),
            portfolio_id=portfolio_id,
            generated_at_utc=generated_at_utc,
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
                    is_terminal_failure=self._is_terminal_failure_status(run.status),
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
        generated_at_utc = datetime.now(timezone.utc)
        run = await self.repo.get_reconciliation_run(
            portfolio_id=portfolio_id,
            run_id=run_id,
            as_of=generated_at_utc,
        )
        if run is None:
            raise ValueError(f"Reconciliation run {run_id} not found for portfolio {portfolio_id}")
        total, findings = await self._read_count_and_page(
            self.repo.get_reconciliation_findings_count(
                run_id=run_id,
                finding_id=finding_id,
                security_id=security_id,
                transaction_id=transaction_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_reconciliation_findings(
                run_id=run_id,
                limit=limit,
                finding_id=finding_id,
                security_id=security_id,
                transaction_id=transaction_id,
                as_of=generated_at_utc,
            ),
        )
        return ReconciliationFindingListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[
                    finding.business_date
                    or getattr(run, "business_date", None)
                    or finding.created_at.date()
                    for finding in findings
                ],
                evidence_timestamps=[finding.created_at for finding in findings],
                reconciliation_status=self._aggregate_reconciliation_finding_status(
                    findings, total
                ),
            ),
            run_id=run_id,
            generated_at_utc=generated_at_utc,
            total=total,
            items=[
                ReconciliationFindingRecord(
                    finding_id=finding.finding_id,
                    finding_type=finding.finding_type,
                    severity=finding.severity,
                    security_id=normalize_security_id(finding.security_id),
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
        generated_at_utc = datetime.now(timezone.utc)
        normalized_status = self._normalize_support_status_filter(status)
        total, stages = await self._read_count_and_page(
            self.repo.get_portfolio_control_stages_count(
                portfolio_id=portfolio_id,
                stage_id=stage_id,
                stage_name=stage_name,
                business_date=business_date,
                status=normalized_status,
                as_of=generated_at_utc,
            ),
            self.repo.get_portfolio_control_stages(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                stage_id=stage_id,
                stage_name=stage_name,
                business_date=business_date,
                status=normalized_status,
                as_of=generated_at_utc,
            ),
        )
        return PortfolioControlStageListResponse(
            portfolio_id=portfolio_id,
            generated_at_utc=generated_at_utc,
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
        normalized_status = self._normalize_support_status_filter(status)
        total, keys = await self._read_count_and_page(
            self.repo.get_reprocessing_keys_count(
                portfolio_id=portfolio_id,
                status=normalized_status,
                security_id=security_id,
                watermark_date=watermark_date,
                as_of=generated_at_utc,
            ),
            self.repo.get_reprocessing_keys(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=normalized_status,
                security_id=security_id,
                watermark_date=watermark_date,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
        )
        return ReprocessingKeyListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[key.watermark_date for key in keys],
                evidence_timestamps=[key.updated_at for key in keys],
            ),
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                ReprocessingKeyRecord(
                    security_id=normalize_security_id(key.security_id),
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
    ) -> ReprocessingJobListResponse:
        await self._ensure_portfolio_exists(portfolio_id)
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        normalized_status = self._normalize_support_status_filter(status)
        total, jobs = await self._read_count_and_page(
            self.repo.get_reprocessing_jobs_count(
                portfolio_id=portfolio_id,
                status=normalized_status,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                as_of=generated_at_utc,
            ),
            self.repo.get_reprocessing_jobs(
                portfolio_id=portfolio_id,
                skip=skip,
                limit=limit,
                status=normalized_status,
                security_id=security_id,
                job_id=job_id,
                correlation_id=correlation_id,
                stale_minutes=stale_minutes,
                reference_now=generated_at_utc,
                as_of=generated_at_utc,
            ),
        )
        return ReprocessingJobListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[date.fromisoformat(job.business_date) for job in jobs],
                evidence_timestamps=[job.updated_at or job.created_at for job in jobs],
            ),
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
        if cls._normalize_support_job_status(status) != "PROCESSING" or updated_at is None:
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
        normalized_status = cls._normalize_support_job_status(status)
        normalized_status = (
            "PROCESSING" if normalized_status == "REPROCESSING" else normalized_status
        )
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
