"""Coordinate Query Control Plane operational support use cases."""

from collections.abc import Awaitable
from datetime import date, datetime, timezone
from typing import Any, TypeVar, cast

from portfolio_common.domain.tenant import TenantId
from portfolio_common.identifiers import normalize_lookup_identifier as normalize_security_id
from portfolio_common.logging_utils import redact_sensitive_text
from portfolio_common.monitoring import observe_outbox_recovery_attempt
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    BREAK_OPEN,
    COMPLETE,
    PARTIAL,
    STALE,
    UNKNOWN,
    ReconciliationRunSignal,
    aggregate_reconciliation_statuses,
    classify_finding_status,
    classify_reconciliation_status,
    evidence_age_minutes,
    is_evidence_stale,
)

from ...application.operations.errors import OutboxRecoveryRejected
from ...contracts.operations import (
    AnalyticsExportJobListResponse,
    CalculatorSloResponse,
    FailedOutboxEventListResponse,
    FailedOutboxEventRecord,
    FailedOutboxRequeueRequest,
    FailedOutboxRequeueResponse,
    LineageKeyListResponse,
    LineageKeyRecord,
    LineageResponse,
    LoadRunProgressResponse,
    OutboxRecoveryAuditListResponse,
    OutboxRecoveryAuditRecord,
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
from ...domain.operations import (
    LineageKeyEvidence,
    MissingHistoricalFxDependencySummary,
    PortfolioControlStageEvidence,
    ReconciliationFindingSummary,
    ReconciliationRunEvidence,
    SnapshotValuationCoverageSummary,
)
from ...ports.operations import OperationsSupportRepository
from .analytics_export_listing import (
    analytics_export_backlog_age_minutes,
    build_analytics_export_job_list_response,
)
from .calculator_slo import build_calculator_slo_response
from .load_run_progress import build_load_run_progress_response
from .policy import (
    DEFAULT_SUPPORT_FAILED_WINDOW_HOURS,
    DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
)
from .portfolio_readiness import (
    PortfolioReadinessSnapshot,
    build_portfolio_readiness_response,
)
from .runtime_state import (
    analytics_export_operational_state,
    evidence_product_runtime_metadata,
    is_analytics_export_job_stale,
    normalize_analytics_export_status,
    normalize_analytics_export_status_filter,
    reconciliation_evidence_identity,
)
from .support_jobs import (
    build_support_job_record,
    get_support_job_operational_state,
    is_support_job_retrying,
    is_support_job_stale,
    is_terminal_failure_status,
    normalize_support_job_status,
    parse_support_job_business_date,
)
from .support_overview import (
    SupportOverviewSnapshot,
    build_support_overview_response,
)

_PagedRowT = TypeVar("_PagedRowT")
MAX_OUTBOX_RECOVERY_REASON_LENGTH = 512


class OperationsService:
    def __init__(self, repository: OperationsSupportRepository, *, tenant_id: str):
        self.repo = repository
        self._tenant_id = TenantId(tenant_id).value

    @staticmethod
    def _evidence_product_runtime_metadata(
        *,
        generated_at_utc: datetime,
        as_of_dates: list[date | None],
        evidence_timestamps: list[datetime | None],
        reconciliation_status: str = UNKNOWN,
        content_hash: str | None = None,
        source_refs: list[str] | None = None,
        source_evidence_current: bool | None = None,
        freshness_status: str | None = None,
    ) -> dict[str, object]:
        return evidence_product_runtime_metadata(
            generated_at_utc=generated_at_utc,
            as_of_dates=as_of_dates,
            evidence_timestamps=evidence_timestamps,
            reconciliation_status=reconciliation_status,
            content_hash=content_hash,
            source_refs=source_refs,
            source_evidence_current=source_evidence_current,
            freshness_status=freshness_status,
        )

    @staticmethod
    def _aggregate_reconciliation_run_status(
        runs: list[object],
        *,
        generated_at_utc: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        statuses = [
            classify_reconciliation_status(
                ReconciliationRunSignal(
                    run_status=getattr(run, "status", None),
                    has_run=True,
                    error_count=OperationsService._summary_count(
                        getattr(run, "summary", None), "error_count"
                    ),
                    warning_count=OperationsService._summary_count(
                        getattr(run, "summary", None), "warning_count"
                    ),
                    is_stale=(
                        OperationsService._reconciliation_evidence_is_stale(
                            evidence_timestamp=OperationsService._run_evidence_timestamp(run),
                            generated_at_utc=generated_at_utc,
                            stale_threshold_minutes=stale_threshold_minutes,
                        )
                        if generated_at_utc is not None
                        else False
                    ),
                )
            )
            for run in runs
        ]
        return OperationsService._aggregate_statuses(statuses)

    @staticmethod
    def _aggregate_reconciliation_finding_status(findings: list[object], total: int) -> str:
        if not findings:
            return cast(str, COMPLETE if total == 0 else UNKNOWN)
        statuses = [
            classify_finding_status(
                severity=str(getattr(finding, "severity", "")),
                resolution_state=str(getattr(finding, "resolution_state", "OPEN")),
            )
            for finding in findings
        ]
        return OperationsService._aggregate_statuses(statuses)

    @staticmethod
    def _aggregate_statuses(statuses: list[str]) -> str:
        return aggregate_reconciliation_statuses(statuses)

    @staticmethod
    def _normalize_support_job_status(status: str | None) -> str | None:
        return normalize_support_job_status(status)

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
        return get_support_job_operational_state(
            status,
            updated_at,
            now,
            stale_threshold_minutes,
        )

    @classmethod
    def _is_terminal_failure_status(cls, status: str | None) -> bool:
        return is_terminal_failure_status(status)

    @classmethod
    def _is_support_job_retrying(cls, status: str, attempt_count: int | None) -> bool:
        return is_support_job_retrying(status, attempt_count)

    @staticmethod
    def _normalize_analytics_export_status(status: str | None) -> str | None:
        return normalize_analytics_export_status(status)

    @classmethod
    def _normalize_analytics_export_status_filter(cls, status: str | None) -> str | None:
        return normalize_analytics_export_status_filter(status)

    @classmethod
    def _get_analytics_export_operational_state(
        cls,
        status: str,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        return analytics_export_operational_state(
            status,
            updated_at,
            now,
            stale_threshold_minutes,
        )

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
        return bool(
            classify_finding_status(
                severity=str(severity or "UNKNOWN"),
                resolution_state="OPEN",
            )
            == BLOCKED
        )

    @classmethod
    def _get_reconciliation_finding_operational_state(
        cls,
        severity: str | None,
        resolution_state: str = "OPEN",
    ) -> str:
        status = cast(
            str,
            classify_finding_status(
                severity=str(severity or "UNKNOWN"),
                resolution_state=resolution_state,
            ),
        )
        if status == COMPLETE:
            return "RESOLVED"
        return "BLOCKING" if status == BLOCKED else "NON_BLOCKING"

    @staticmethod
    def _run_evidence_timestamp(run: object) -> datetime | None:
        return cast(
            datetime | None,
            getattr(run, "completed_at", None)
            or getattr(run, "updated_at", None)
            or getattr(run, "started_at", None),
        )

    @staticmethod
    def _reconciliation_evidence_is_stale(
        *,
        evidence_timestamp: datetime | None,
        generated_at_utc: datetime | None,
        stale_threshold_minutes: int,
    ) -> bool:
        if generated_at_utc is None:
            return False
        return bool(
            is_evidence_stale(
                evidence_age_minutes=evidence_age_minutes(
                    generated_at=generated_at_utc,
                    evidence_timestamp=evidence_timestamp,
                ),
                threshold_minutes=stale_threshold_minutes,
            ),
        )

    @staticmethod
    def _summary_count(summary: object, key: str) -> int:
        value = getattr(summary, "get", lambda *_: 0)(key, 0) if summary is not None else 0
        return int(value or 0)

    @staticmethod
    def _publication_block_reasons(
        *,
        reconciliation_status: str,
        evidence_age: int | None,
        stale_threshold_minutes: int,
        has_open_blocking_findings: bool = False,
        has_open_nonblocking_findings: bool = False,
    ) -> list[str]:
        reasons: list[str] = []
        if has_open_blocking_findings or reconciliation_status == BLOCKED:
            reasons.append("OPEN_BLOCKING_RECONCILIATION_EVIDENCE")
        if has_open_nonblocking_findings or reconciliation_status in {BREAK_OPEN, PARTIAL}:
            reasons.append("NON_COMPLETE_RECONCILIATION_EVIDENCE")
        if reconciliation_status == STALE or is_evidence_stale(
            evidence_age_minutes=evidence_age,
            threshold_minutes=stale_threshold_minutes,
        ):
            reasons.append("STALE_RECONCILIATION_EVIDENCE")
        if evidence_age is None:
            reasons.append("MISSING_RECONCILIATION_EVIDENCE_TIMESTAMP")
        if reconciliation_status != COMPLETE and not reasons:
            reasons.append("UNSAFE_RECONCILIATION_STATUS")
        return list(dict.fromkeys(reasons))

    @classmethod
    def _get_reprocessing_key_operational_state(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> str:
        normalized_status = cls._normalize_support_job_status(status)
        if normalized_status == "SNAPSHOT_ONLY":
            return "SNAPSHOT_ONLY"
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
        if normalized_reprocessing_status == "SNAPSHOT_ONLY":
            return "SNAPSHOT_ONLY"
        if normalized_reprocessing_status == "REPROCESSING":
            return "REPLAYING"
        if has_artifact_gap:
            if normalized_valuation_status == "FAILED":
                return "VALUATION_BLOCKED"
            return "ARTIFACT_GAP"
        return "HEALTHY"

    def _build_lineage_key_record(self, key: LineageKeyEvidence) -> LineageKeyRecord:
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
        business_date: date | None,
        status: str,
        security_id: str | None,
        epoch: int | None,
        attempt_count: int | None,
        correlation_id: str | None,
        created_at: datetime | None,
        updated_at: datetime | None,
        failure_reason: str | None,
        from_currency: str | None = None,
        to_currency: str | None = None,
        reference_now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
        stale_deadline: datetime | None = None,
    ) -> SupportJobRecord:
        return build_support_job_record(
            job_id=job_id,
            job_type=job_type,
            business_date=business_date,
            status=status,
            security_id=security_id,
            epoch=epoch,
            attempt_count=attempt_count,
            correlation_id=correlation_id,
            created_at=created_at,
            updated_at=updated_at,
            failure_reason=failure_reason,
            from_currency=from_currency,
            to_currency=to_currency,
            reference_now=reference_now,
            stale_threshold_minutes=stale_threshold_minutes,
            stale_deadline=stale_deadline,
        )

    async def _ensure_portfolio_exists(self, portfolio_id: str) -> None:
        if not await self.repo.portfolio_exists_for_tenant(
            tenant_id=self._tenant_id,
            portfolio_id=portfolio_id,
        ):
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

    async def _resolve_portfolio_latest_business_date(
        self,
        portfolio_id: str,
        *,
        generated_at_utc: datetime,
    ) -> date | None:
        await self._ensure_portfolio_exists(portfolio_id)
        return await self.repo.get_latest_business_date(as_of=generated_at_utc)

    async def _read_count_and_page(
        self,
        count_read: Awaitable[int],
        page_read: Awaitable[list[_PagedRowT]],
    ) -> tuple[int, list[_PagedRowT]]:
        try:
            total = await count_read
        except Exception:
            close = getattr(page_read, "close", None)
            if callable(close):
                close()
            raise
        rows = await page_read
        return total, rows

    async def _read_latest_reconciliation_evidence(
        self,
        *,
        portfolio_id: str,
        latest_control_stage: PortfolioControlStageEvidence | None,
    ) -> tuple[ReconciliationRunEvidence | None, ReconciliationFindingSummary | None]:
        if latest_control_stage is None:
            return None, None

        latest_reconciliation_run = await self.repo.get_latest_reconciliation_run_for_portfolio_day(
            portfolio_id=portfolio_id,
            business_date=latest_control_stage.business_date,
            epoch=latest_control_stage.epoch,
            as_of=latest_control_stage.updated_at,
        )
        if latest_reconciliation_run is None:
            return None, None

        latest_reconciliation_finding_summary = await self.repo.get_reconciliation_finding_summary(
            latest_reconciliation_run.run_id,
            as_of=latest_control_stage.updated_at,
        )
        return latest_reconciliation_run, latest_reconciliation_finding_summary

    async def _read_latest_booked_dates(
        self,
        *,
        portfolio_id: str,
        latest_business_date: date | None,
        generated_at_utc: datetime,
    ) -> tuple[date | None, date | None]:
        if latest_business_date is None:
            return None, None

        latest_booked_transaction_date = await self.repo.get_latest_transaction_date_as_of(
            portfolio_id,
            latest_business_date,
            snapshot_as_of=generated_at_utc,
        )
        latest_booked_position_snapshot_date = (
            await self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                portfolio_id,
                latest_business_date,
                snapshot_as_of=generated_at_utc,
            )
        )
        return latest_booked_transaction_date, latest_booked_position_snapshot_date

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
        as_of_date: date | None = None,
        use_latest_business_date_for_aggregation_health: bool = False,
    ) -> SupportOverviewResponse:
        generated_at_utc = datetime.now(timezone.utc)
        latest_business_date = await self._resolve_portfolio_latest_business_date(
            portfolio_id,
            generated_at_utc=generated_at_utc,
        )
        aggregation_health_through_date = as_of_date
        if (
            aggregation_health_through_date is None
            and use_latest_business_date_for_aggregation_health
        ):
            aggregation_health_through_date = latest_business_date
        current_epoch = await self.repo.get_current_portfolio_epoch(
            portfolio_id,
            as_of=generated_at_utc,
        )
        reprocessing_health = await self.repo.get_reprocessing_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
        )
        valuation_job_health = await self.repo.get_valuation_job_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
        )
        aggregation_job_health = await self.repo.get_aggregation_job_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
            through_business_date=aggregation_health_through_date,
        )
        analytics_export_job_health = await self.repo.get_analytics_export_job_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
        )
        latest_transaction_date = await self.repo.get_latest_transaction_date(
            portfolio_id,
            as_of=generated_at_utc,
        )
        latest_position_snapshot_date_unbounded = (
            await self.repo.get_latest_snapshot_date_for_current_epoch(
                portfolio_id,
                as_of=generated_at_utc,
            )
        )
        position_snapshot_history_mismatch_count = (
            await self.repo.get_position_snapshot_history_mismatch_count(
                portfolio_id,
                as_of=generated_at_utc,
            )
        )
        latest_control_stage = await self.repo.get_latest_financial_reconciliation_control_stage(
            portfolio_id,
            as_of=generated_at_utc,
        )
        (
            latest_reconciliation_run,
            latest_reconciliation_finding_summary,
        ) = await self._read_latest_reconciliation_evidence(
            portfolio_id=portfolio_id,
            latest_control_stage=latest_control_stage,
        )
        (
            latest_booked_transaction_date,
            latest_booked_position_snapshot_date,
        ) = await self._read_latest_booked_dates(
            portfolio_id=portfolio_id,
            latest_business_date=latest_business_date,
            generated_at_utc=generated_at_utc,
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
            as_of_date=as_of_date,
            stale_threshold_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            use_latest_business_date_for_aggregation_health=True,
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
            latest_booked_transaction_date = await self.repo.get_latest_transaction_date_as_of(
                portfolio_id,
                resolved_as_of_date,
                snapshot_as_of=generated_at_utc,
            )
            latest_booked_position_snapshot_date = (
                await self.repo.get_latest_snapshot_date_for_current_epoch_as_of(
                    portfolio_id,
                    resolved_as_of_date,
                    snapshot_as_of=generated_at_utc,
                )
            )
            missing_fx_summary = await self.repo.get_missing_historical_fx_dependency_summary(
                portfolio_id,
                resolved_as_of_date,
                snapshot_as_of=generated_at_utc,
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
        reprocessing_health = await self.repo.get_reprocessing_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
        )
        valuation_job_health = await self.repo.get_valuation_job_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
        )
        aggregation_job_health = await self.repo.get_aggregation_job_health_summary(
            portfolio_id,
            stale_minutes=stale_threshold_minutes,
            failed_window_hours=failed_window_hours,
            reference_now=generated_at_utc,
            as_of=generated_at_utc,
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
        await self._ensure_portfolio_exists(portfolio_id)
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

        latest_history_date = await self.repo.get_latest_position_history_date(
            portfolio_id,
            security_id,
            position_state.epoch,
            as_of=generated_at_utc,
        )
        latest_snapshot_date = await self.repo.get_latest_daily_snapshot_date(
            portfolio_id,
            security_id,
            position_state.epoch,
            as_of=generated_at_utc,
        )
        latest_valuation_job = await self.repo.get_latest_valuation_job(
            portfolio_id,
            security_id,
            position_state.epoch,
            as_of=generated_at_utc,
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
        normalized_status = self._normalize_support_status_filter(status)
        generated_at_utc, total, jobs = await self.repo.get_valuation_jobs_snapshot(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            stale_threshold_minutes=stale_threshold_minutes,
            status=normalized_status,
            business_date=business_date,
            security_id=security_id,
            job_id=job_id,
            correlation_id=correlation_id,
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
                    stale_deadline=job.valuation_lease_expires_at,
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
        normalized_status = self._normalize_support_status_filter(status)
        generated_at_utc, total, jobs = await self.repo.get_aggregation_jobs_snapshot(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            stale_threshold_minutes=stale_threshold_minutes,
            status=normalized_status,
            business_date=business_date,
            job_id=job_id,
            correlation_id=correlation_id,
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
                    stale_deadline=job.lease_expires_at,
                )
                for job in jobs
            ],
        )

    async def get_analytics_export_jobs(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        skip: int,
        limit: int,
        status: str | None = None,
        job_id: str | None = None,
        request_fingerprint: str | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> AnalyticsExportJobListResponse:
        if not await self.repo.portfolio_exists_for_tenant(
            tenant_id=tenant_id, portfolio_id=portfolio_id
        ):
            raise ValueError(f"Portfolio {portfolio_id} not found")
        generated_at_utc = datetime.now(timezone.utc)
        stale_minutes = stale_threshold_minutes
        normalized_status = self._normalize_analytics_export_status_filter(status)
        total, jobs = await self._read_count_and_page(
            self.repo.get_analytics_export_jobs_count(
                tenant_id=tenant_id,
                portfolio_id=portfolio_id,
                status=normalized_status,
                job_id=job_id,
                request_fingerprint=request_fingerprint,
                as_of=generated_at_utc,
            ),
            self.repo.get_analytics_export_jobs(
                tenant_id=tenant_id,
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
        return build_analytics_export_job_list_response(
            portfolio_id=portfolio_id,
            stale_threshold_minutes=stale_threshold_minutes,
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            jobs=jobs,
        )

    async def get_failed_outbox_events(
        self,
        *,
        skip: int,
        limit: int,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        topic: str | None = None,
        correlation_id: str | None = None,
        reason_code: str | None = None,
    ) -> FailedOutboxEventListResponse:
        generated_at_utc = datetime.now(timezone.utc)
        total, events = await self._read_count_and_page(
            self.repo.get_failed_outbox_events_count(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                topic=topic,
                correlation_id=correlation_id,
                reason_code=reason_code,
                as_of=generated_at_utc,
            ),
            self.repo.get_failed_outbox_events(
                skip=skip,
                limit=limit,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                topic=topic,
                correlation_id=correlation_id,
                reason_code=reason_code,
                as_of=generated_at_utc,
            ),
        )
        return FailedOutboxEventListResponse(
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                FailedOutboxEventRecord(
                    outbox_id=event.id,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    event_type=event.event_type,
                    topic=event.topic,
                    status="FAILED",
                    correlation_id=event.correlation_id,
                    retry_count=event.retry_count or 0,
                    last_attempted_at=event.last_attempted_at,
                    next_attempt_at=event.next_attempt_at,
                    last_failure_reason_code=event.last_failure_reason_code,
                    last_failure_category=event.last_failure_category,
                    last_failure_message=event.last_failure_message,
                    last_failure_at=event.last_failure_at,
                    created_at=event.created_at,
                    processed_at=event.processed_at,
                    retry_safe=False,
                    recommended_recovery_action="inspect_payload_contract_before_requeue",
                )
                for event in events
            ],
        )

    async def requeue_failed_outbox_event(
        self,
        *,
        outbox_id: int,
        request: FailedOutboxRequeueRequest,
    ) -> FailedOutboxRequeueResponse:
        requested_at = datetime.now(timezone.utc)
        try:
            audit, event = await self.repo.requeue_failed_outbox_event(
                outbox_id=outbox_id,
                requested_by=request.requested_by.strip(),
                reason=_source_safe_outbox_recovery_reason(request.reason),
                correlation_id=(
                    request.correlation_id.strip() if request.correlation_id is not None else None
                ),
                confirm_payload_contract_reviewed=request.confirm_payload_contract_reviewed,
                requested_at=requested_at,
            )
        except OutboxRecoveryRejected as exc:
            observe_outbox_recovery_attempt(
                "requeue_failed_outbox",
                "REJECTED",
                _outbox_recovery_metric_reason(exc.metadata.get("reason")),
            )
            raise
        except ValueError:
            observe_outbox_recovery_attempt(
                "requeue_failed_outbox",
                "NOT_FOUND",
                "outbox_row_not_found",
            )
            raise
        except Exception:
            observe_outbox_recovery_attempt(
                "requeue_failed_outbox",
                "ERROR",
                "unexpected_error",
            )
            raise
        completed_at = audit.completed_at or requested_at
        observe_outbox_recovery_attempt(
            "requeue_failed_outbox",
            "REQUEUED",
            "outbox_row_requeued_for_dispatch",
        )
        return FailedOutboxRequeueResponse(
            outbox_id=event.id,
            audit_id=audit.id,
            prior_status="FAILED",
            new_status="PENDING",
            outcome="REQUEUED",
            requested_by=audit.requested_by,
            reason=audit.reason,
            correlation_id=audit.correlation_id,
            requested_at_utc=audit.requested_at,
            completed_at_utc=completed_at,
            retry_count=event.retry_count or 0,
            next_attempt_at=event.next_attempt_at or completed_at,
        )

    async def get_outbox_recovery_audits(
        self,
        *,
        skip: int,
        limit: int,
        outbox_id: int | None = None,
        outcome: str | None = None,
        correlation_id: str | None = None,
        requested_by: str | None = None,
        recovery_action: str | None = None,
    ) -> OutboxRecoveryAuditListResponse:
        generated_at_utc = datetime.now(timezone.utc)
        total, audits = await self._read_count_and_page(
            self.repo.get_outbox_recovery_audits_count(
                outbox_id=outbox_id,
                outcome=outcome,
                correlation_id=correlation_id,
                requested_by=requested_by,
                recovery_action=recovery_action,
                as_of=generated_at_utc,
            ),
            self.repo.get_outbox_recovery_audits(
                skip=skip,
                limit=limit,
                outbox_id=outbox_id,
                outcome=outcome,
                correlation_id=correlation_id,
                requested_by=requested_by,
                recovery_action=recovery_action,
                as_of=generated_at_utc,
            ),
        )
        return OutboxRecoveryAuditListResponse(
            generated_at_utc=generated_at_utc,
            total=total,
            skip=skip,
            limit=limit,
            items=[
                OutboxRecoveryAuditRecord(
                    audit_id=audit.id,
                    outbox_id=audit.outbox_id,
                    recovery_action=audit.recovery_action,
                    requested_by=audit.requested_by,
                    reason=audit.reason,
                    correlation_id=audit.correlation_id,
                    prior_status=audit.prior_status,
                    new_status=audit.new_status,
                    outcome=audit.outcome,
                    outcome_message=audit.outcome_message,
                    prior_retry_count=audit.prior_retry_count,
                    prior_last_failure_reason_code=audit.prior_last_failure_reason_code,
                    prior_last_failure_category=audit.prior_last_failure_category,
                    prior_last_failure_message=audit.prior_last_failure_message,
                    prior_last_failure_at=audit.prior_last_failure_at,
                    requested_at_utc=audit.requested_at,
                    completed_at_utc=audit.completed_at,
                )
                for audit in audits
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
        stale_threshold_minutes = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES
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
        finding_summaries = await self.repo.get_reconciliation_finding_summaries(
            [run.run_id for run in runs],
            as_of=generated_at_utc,
        )
        current_finding_summaries = {
            run.run_id: finding_summaries.get(
                run.run_id,
                self._empty_reconciliation_finding_summary(),
            )
            for run in runs
        }
        items = [
            self._build_reconciliation_run_record(
                run,
                finding_summary=current_finding_summaries[run.run_id],
                generated_at_utc=generated_at_utc,
                stale_threshold_minutes=stale_threshold_minutes,
            )
            for run in runs
        ]
        reconciliation_status = self._aggregate_statuses(
            [item.normalized_reconciliation_status for item in items]
        )
        evidence_timestamps = [
            max(
                (
                    timestamp
                    for timestamp in (
                        self._run_evidence_timestamp(run),
                        current_finding_summaries[run.run_id].latest_evidence_at,
                    )
                    if timestamp is not None
                ),
                default=None,
            )
            for run in runs
        ]
        latest_evidence_timestamp = max(
            (timestamp for timestamp in evidence_timestamps if timestamp is not None),
            default=None,
        )
        bundle_evidence_age = evidence_age_minutes(
            generated_at=generated_at_utc,
            evidence_timestamp=latest_evidence_timestamp,
        )
        publication_block_reasons = self._publication_block_reasons(
            reconciliation_status=reconciliation_status,
            evidence_age=bundle_evidence_age,
            stale_threshold_minutes=stale_threshold_minutes,
        )
        if skip > 0 or total > len(runs):
            publication_block_reasons = [
                *publication_block_reasons,
                "INCOMPLETE_RECONCILIATION_EVIDENCE_WINDOW",
            ]
        latest_run = max(runs, key=lambda run: run.started_at, default=None)
        open_break_count_by_severity = {
            severity: count
            for severity in ("BLOCKER", "CRITICAL", "ERROR", "WARNING", "INFO")
            if (
                count := sum(
                    self._finding_severity_counts(current_finding_summaries[run.run_id]).get(
                        severity, 0
                    )
                    for run in runs
                )
            )
        }
        top_blocking_run_id = next(
            (item.run_id for item in items if item.normalized_reconciliation_status == BLOCKED),
            None,
        )
        evidence_payload: dict[str, object] = {
            "product_name": "ReconciliationEvidenceBundle",
            "product_version": "v1",
            "projection": "runs",
            "portfolio_id": portfolio_id,
            "filters": {
                "run_id": run_id,
                "correlation_id": correlation_id,
                "requested_by": requested_by,
                "dedupe_key": dedupe_key,
                "reconciliation_type": reconciliation_type,
                "status": normalized_status,
            },
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": [
                item.model_dump(
                    mode="json",
                    exclude={"evidence_age_minutes", "is_evidence_stale"},
                )
                for item in items
            ],
        }
        reconciliation_evidence_id, content_hash = reconciliation_evidence_identity(
            evidence_payload
        )
        source_refs = sorted(
            f"lotus-core://source/FinancialReconciliationRun/{run.run_id}" for run in runs
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
                evidence_timestamps=evidence_timestamps,
                reconciliation_status=reconciliation_status,
                content_hash=content_hash,
                source_refs=source_refs,
                source_evidence_current=not publication_block_reasons,
                freshness_status=(
                    "CURRENT"
                    if not publication_block_reasons
                    else "STALE"
                    if "STALE_RECONCILIATION_EVIDENCE" in publication_block_reasons
                    else "PARTIAL"
                ),
            ),
            portfolio_id=portfolio_id,
            generated_at_utc=generated_at_utc,
            reconciliation_evidence_id=reconciliation_evidence_id,
            latest_run_id=getattr(latest_run, "run_id", None),
            open_break_count_by_severity=open_break_count_by_severity,
            top_blocking_run_id=top_blocking_run_id,
            stale_threshold_minutes=stale_threshold_minutes,
            evidence_age_minutes=bundle_evidence_age,
            publication_gate="BLOCK" if publication_block_reasons else "ALLOW",
            publication_block_reasons=publication_block_reasons,
            total=total,
            skip=skip,
            limit=limit,
            items=items,
        )

    def _build_reconciliation_run_record(
        self,
        run: Any,
        *,
        finding_summary: ReconciliationFindingSummary,
        generated_at_utc: datetime,
        stale_threshold_minutes: int,
    ) -> ReconciliationRunRecord:
        evidence_timestamp = max(
            (
                timestamp
                for timestamp in (
                    self._run_evidence_timestamp(run),
                    finding_summary.latest_evidence_at,
                )
                if timestamp is not None
            ),
            default=None,
        )
        age_minutes = evidence_age_minutes(
            generated_at=generated_at_utc,
            evidence_timestamp=evidence_timestamp,
        )
        run_normalized_status = classify_reconciliation_status(
            ReconciliationRunSignal(
                run_status=cast(str | None, getattr(run, "status", None)),
                has_run=True,
                is_stale=is_evidence_stale(
                    evidence_age_minutes=age_minutes,
                    threshold_minutes=stale_threshold_minutes,
                ),
            )
        )
        normalized_status = self._finding_summary_reconciliation_status(
            finding_summary,
            run_normalized_status=run_normalized_status,
        )
        return ReconciliationRunRecord(
            run_id=run.run_id,
            reconciliation_type=run.reconciliation_type,
            status=run.status,
            business_date=run.business_date,
            epoch=run.epoch,
            aggregation_revision=run.aggregation_revision,
            started_at=run.started_at,
            completed_at=run.completed_at,
            requested_by=run.requested_by,
            dedupe_key=run.dedupe_key,
            correlation_id=run.correlation_id,
            failure_reason=run.failure_reason,
            tolerance=getattr(run, "tolerance", None),
            summary=getattr(run, "summary", None),
            open_break_count=finding_summary.open_findings,
            blocking_break_count=finding_summary.blocking_findings,
            open_break_count_by_severity=self._finding_severity_counts(finding_summary),
            top_blocking_finding_id=finding_summary.top_blocking_finding_id,
            normalized_reconciliation_status=normalized_status,
            evidence_age_minutes=age_minutes or 0,
            is_evidence_stale=is_evidence_stale(
                evidence_age_minutes=age_minutes,
                threshold_minutes=stale_threshold_minutes,
            ),
            is_terminal_failure=self._is_terminal_failure_status(run.status),
            is_blocking=normalized_status == BLOCKED,
            operational_state=self._get_reconciliation_operational_state(run.status),
        )

    @staticmethod
    def _empty_reconciliation_finding_summary() -> ReconciliationFindingSummary:
        return ReconciliationFindingSummary(
            total_findings=0,
            blocking_findings=0,
            top_blocking_finding_id=None,
            top_blocking_finding_type=None,
            top_blocking_finding_security_id=None,
            top_blocking_finding_transaction_id=None,
        )

    @staticmethod
    def _finding_severity_counts(
        summary: ReconciliationFindingSummary,
    ) -> dict[str, int]:
        return {
            severity: count
            for severity, count in (
                ("BLOCKER", summary.blocker_findings),
                ("CRITICAL", summary.critical_findings),
                ("ERROR", summary.error_findings),
                ("WARNING", summary.warning_findings),
                ("INFO", summary.info_findings),
            )
            if count
        }

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
        finding_summary = await self.repo.get_reconciliation_finding_summary(
            run_id=run_id,
            finding_id=finding_id,
            security_id=security_id,
            transaction_id=transaction_id,
            as_of=generated_at_utc,
        )
        findings = await self.repo.get_reconciliation_findings(
            run_id=run_id,
            limit=limit,
            finding_id=finding_id,
            security_id=security_id,
            transaction_id=transaction_id,
            as_of=generated_at_utc,
        )
        total = finding_summary.total_findings
        stale_threshold_minutes = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES
        items = [
            self._build_reconciliation_finding_record(
                finding,
                generated_at_utc=generated_at_utc,
            )
            for finding in findings
        ]
        run_evidence_timestamp = self._run_evidence_timestamp(run)
        latest_evidence_timestamp = max(
            (
                timestamp
                for timestamp in (
                    finding_summary.latest_evidence_at,
                    run_evidence_timestamp,
                )
                if timestamp is not None
            ),
            default=None,
        )
        bundle_evidence_age = evidence_age_minutes(
            generated_at=generated_at_utc,
            evidence_timestamp=latest_evidence_timestamp,
        )
        run_normalized_status = classify_reconciliation_status(
            ReconciliationRunSignal(
                run_status=getattr(run, "status", None),
                error_count=finding_summary.blocking_findings,
                warning_count=(finding_summary.warning_findings + finding_summary.info_findings),
                is_stale=is_evidence_stale(
                    evidence_age_minutes=bundle_evidence_age,
                    threshold_minutes=stale_threshold_minutes,
                ),
            )
        )
        reconciliation_status = self._finding_summary_reconciliation_status(
            finding_summary,
            run_normalized_status=run_normalized_status,
        )
        publication_block_reasons = self._publication_block_reasons(
            reconciliation_status=reconciliation_status,
            evidence_age=bundle_evidence_age,
            stale_threshold_minutes=stale_threshold_minutes,
            has_open_blocking_findings=finding_summary.blocking_findings > 0,
            has_open_nonblocking_findings=(
                finding_summary.open_findings > finding_summary.blocking_findings
            ),
        )
        open_break_count_by_severity = {
            severity: count
            for severity, count in (
                ("BLOCKER", finding_summary.blocker_findings),
                ("CRITICAL", finding_summary.critical_findings),
                ("ERROR", finding_summary.error_findings),
                ("WARNING", finding_summary.warning_findings),
                ("INFO", finding_summary.info_findings),
            )
            if count
        }
        evidence_payload: dict[str, object] = {
            "product_name": "ReconciliationEvidenceBundle",
            "product_version": "v1",
            "projection": "findings",
            "portfolio_id": portfolio_id,
            "run_id": run_id,
            "filters": {
                "finding_id": finding_id,
                "security_id": security_id,
                "transaction_id": transaction_id,
            },
            "run_tolerance": getattr(run, "tolerance", None),
            "run_summary": getattr(run, "summary", None),
            "total": total,
            "items": [item.model_dump(mode="json", exclude={"age_days"}) for item in items],
            "open_break_count_by_severity": open_break_count_by_severity,
        }
        reconciliation_evidence_id, content_hash = reconciliation_evidence_identity(
            evidence_payload
        )
        source_refs = [
            f"lotus-core://source/FinancialReconciliationRun/{run_id}",
            *(
                f"lotus-core://source/FinancialReconciliationFinding/{finding.finding_id}"
                for finding in findings
            ),
        ]
        return ReconciliationFindingListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=[
                    finding.business_date
                    or getattr(run, "business_date", None)
                    or finding.created_at.date()
                    for finding in findings
                ],
                evidence_timestamps=[latest_evidence_timestamp],
                reconciliation_status=reconciliation_status,
                content_hash=content_hash,
                source_refs=sorted(source_refs),
                source_evidence_current=not publication_block_reasons,
                freshness_status=(
                    "CURRENT"
                    if not publication_block_reasons
                    else "STALE"
                    if "STALE_RECONCILIATION_EVIDENCE" in publication_block_reasons
                    else "PARTIAL"
                ),
            ),
            run_id=run_id,
            generated_at_utc=generated_at_utc,
            reconciliation_evidence_id=reconciliation_evidence_id,
            run_tolerance=getattr(run, "tolerance", None),
            run_summary=getattr(run, "summary", None),
            open_break_count_by_severity=open_break_count_by_severity,
            open_break_count=finding_summary.open_findings,
            blocking_break_count=finding_summary.blocking_findings,
            warning_break_count=(finding_summary.warning_findings + finding_summary.info_findings),
            top_blocking_finding_id=finding_summary.top_blocking_finding_id,
            top_blocking_finding_owner=finding_summary.top_blocking_finding_owner,
            top_blocking_repair_recommendation=(finding_summary.top_blocking_repair_recommendation),
            stale_threshold_minutes=stale_threshold_minutes,
            evidence_age_minutes=bundle_evidence_age,
            publication_gate="BLOCK" if publication_block_reasons else "ALLOW",
            publication_block_reasons=publication_block_reasons,
            total=total,
            items=items,
        )

    @staticmethod
    def _finding_summary_reconciliation_status(
        summary: ReconciliationFindingSummary,
        *,
        run_normalized_status: str,
    ) -> str:
        finding_status = (
            BLOCKED
            if summary.blocking_findings
            else BREAK_OPEN
            if summary.open_findings
            else COMPLETE
        )
        return aggregate_reconciliation_statuses([run_normalized_status, finding_status])

    def _build_reconciliation_finding_record(
        self,
        finding: Any,
        *,
        generated_at_utc: datetime,
    ) -> ReconciliationFindingRecord:
        resolution_state = str(getattr(finding, "resolution_state", "OPEN"))
        resolution_actor = getattr(finding, "resolution_actor", None)
        resolved_at = getattr(finding, "resolved_at", None)
        if resolved_at is not None and resolved_at > generated_at_utc:
            resolution_state = "OPEN"
            resolution_actor = None
            resolved_at = None
        normalized_status = classify_finding_status(
            severity=str(finding.severity),
            resolution_state=resolution_state,
        )
        age_days = max(0, (generated_at_utc.date() - finding.created_at.date()).days)
        return ReconciliationFindingRecord(
            finding_id=finding.finding_id,
            finding_type=finding.finding_type,
            severity=finding.severity,
            security_id=normalize_security_id(finding.security_id),
            transaction_id=finding.transaction_id,
            business_date=finding.business_date,
            epoch=finding.epoch,
            created_at=finding.created_at,
            detail=finding.detail,
            expected_value=getattr(finding, "expected_value", None),
            observed_value=getattr(finding, "observed_value", None),
            owner=getattr(finding, "owner", "FINANCIAL_CONTROL_OPERATIONS"),
            resolution_state=resolution_state,
            resolution_actor=resolution_actor,
            resolved_at=resolved_at,
            tolerance=getattr(finding, "tolerance", None),
            observed_delta=getattr(finding, "observed_delta", None),
            repair_recommendation=getattr(
                finding,
                "repair_recommendation",
                "REVIEW_RECONCILIATION_BREAK",
            ),
            normalized_finding_status=normalized_status,
            age_days=age_days,
            is_blocking=normalized_status == BLOCKED,
            operational_state=self._get_reconciliation_finding_operational_state(
                finding.severity,
                resolution_state,
            ),
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
        normalized_status = self._normalize_support_status_filter(status)
        generated_at_utc, total, jobs = await self.repo.get_reprocessing_jobs_snapshot(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            status=normalized_status,
            security_id=security_id,
            job_id=job_id,
            correlation_id=correlation_id,
        )
        job_business_dates = [parse_support_job_business_date(job.business_date) for job in jobs]
        return ReprocessingJobListResponse(
            **self._evidence_product_runtime_metadata(
                generated_at_utc=generated_at_utc,
                as_of_dates=job_business_dates,
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
                    business_date=job_business_dates[index],
                    status=job.status,
                    security_id=job.security_id,
                    epoch=None,
                    attempt_count=job.attempt_count,
                    correlation_id=job.correlation_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    failure_reason=job.failure_reason,
                    from_currency=job.from_currency,
                    to_currency=job.to_currency,
                    reference_now=generated_at_utc,
                    stale_threshold_minutes=stale_threshold_minutes,
                    stale_deadline=job.lease_expires_at,
                )
                for index, job in enumerate(jobs)
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
        return is_support_job_stale(status, updated_at, now, stale_threshold_minutes)

    @classmethod
    def _is_analytics_export_job_stale(
        cls,
        status: str | None,
        updated_at: datetime | None,
        now: datetime | None = None,
        stale_threshold_minutes: int = DEFAULT_SUPPORT_STALE_THRESHOLD_MINUTES,
    ) -> bool:
        return is_analytics_export_job_stale(
            status,
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
        return analytics_export_backlog_age_minutes(status, created_at, now)


def _source_safe_outbox_recovery_reason(reason: str) -> str:
    redacted_reason = cast(str, redact_sensitive_text(reason.strip()))
    return redacted_reason[:MAX_OUTBOX_RECOVERY_REASON_LENGTH]


def _outbox_recovery_metric_reason(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    return "recovery_rejected"
