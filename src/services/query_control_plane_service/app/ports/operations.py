"""Persistence port for Query Control Plane operational support."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from ..domain.operations import (
    ExportJobHealthSummary,
    JobHealthSummary,
    LineageKeyEvidence,
    LoadRunProgressSummary,
    MissingHistoricalFxDependencySummary,
    PortfolioControlStageEvidence,
    ReconciliationFindingSummary,
    ReconciliationRunEvidence,
    ReprocessingHealthSummary,
    SnapshotValuationCoverageSummary,
)


class OperationsSupportRepository(Protocol):
    """Read and transition the operational evidence required by support use cases."""

    async def portfolio_exists(self, portfolio_id: str) -> bool: ...

    async def get_load_run_progress(
        self,
        run_id: str,
        business_date: date,
        as_of: datetime | None = None,
    ) -> LoadRunProgressSummary: ...

    async def get_current_portfolio_epoch(
        self,
        portfolio_id: str,
        as_of: datetime | None = None,
    ) -> int | None: ...

    async def get_reprocessing_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        reference_now: datetime,
        as_of: datetime | None = None,
    ) -> ReprocessingHealthSummary: ...

    async def get_valuation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: datetime | None = None,
    ) -> JobHealthSummary: ...

    async def get_aggregation_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: datetime | None = None,
    ) -> JobHealthSummary: ...

    async def get_analytics_export_job_health_summary(
        self,
        portfolio_id: str,
        stale_minutes: int,
        failed_window_hours: int,
        reference_now: datetime,
        as_of: datetime | None = None,
    ) -> ExportJobHealthSummary: ...

    async def get_latest_transaction_date(
        self,
        portfolio_id: str,
        as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_transaction_date_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_business_date(
        self,
        as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_snapshot_date_for_current_epoch(
        self,
        portfolio_id: str,
        as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_snapshot_date_for_current_epoch_as_of(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_position_snapshot_history_mismatch_count(
        self,
        portfolio_id: str,
        as_of: datetime | None = None,
    ) -> int: ...

    async def get_snapshot_valuation_coverage_summary(
        self,
        portfolio_id: str,
        snapshot_date: date | None,
        snapshot_as_of: datetime | None = None,
    ) -> SnapshotValuationCoverageSummary: ...

    async def get_missing_historical_fx_dependency_summary(
        self,
        portfolio_id: str,
        as_of_date: date,
        snapshot_as_of: datetime | None = None,
        sample_limit: int = 10,
    ) -> MissingHistoricalFxDependencySummary: ...

    async def get_latest_financial_reconciliation_control_stage(
        self,
        portfolio_id: str,
        as_of: datetime | None = None,
    ) -> PortfolioControlStageEvidence | None: ...

    async def get_latest_reconciliation_run_for_portfolio_day(
        self,
        portfolio_id: str,
        business_date: date,
        epoch: int,
        as_of: datetime | None = None,
    ) -> ReconciliationRunEvidence | None: ...

    async def get_position_state(
        self,
        portfolio_id: str,
        security_id: str,
        as_of: datetime | None = None,
    ) -> Any | None: ...

    async def get_latest_position_history_date(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_daily_snapshot_date(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        as_of: datetime | None = None,
    ) -> date | None: ...

    async def get_latest_valuation_job(
        self,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        as_of: datetime | None = None,
    ) -> Any | None: ...

    async def get_lineage_keys_count(
        self,
        portfolio_id: str,
        reprocessing_status: str | None = None,
        security_id: str | None = None,
        as_of: datetime | None = None,
    ) -> int: ...

    async def get_lineage_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        reprocessing_status: str | None = None,
        security_id: str | None = None,
        as_of: datetime | None = None,
    ) -> list[LineageKeyEvidence]: ...

    async def get_valuation_jobs_count(self, portfolio_id: str, **filters: Any) -> int: ...

    async def get_valuation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_aggregation_jobs_count(self, portfolio_id: str, **filters: Any) -> int: ...

    async def get_aggregation_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_analytics_export_jobs_count(
        self,
        portfolio_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_analytics_export_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_failed_outbox_events_count(self, **filters: Any) -> int: ...

    async def get_failed_outbox_events(
        self,
        *,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def requeue_failed_outbox_event(
        self,
        *,
        outbox_id: int,
        requested_by: str,
        reason: str,
        correlation_id: str | None,
        confirm_payload_contract_reviewed: bool,
        requested_at: datetime,
    ) -> tuple[Any, Any]: ...

    async def get_outbox_recovery_audits_count(self, **filters: Any) -> int: ...

    async def get_outbox_recovery_audits(
        self,
        *,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_reconciliation_runs_count(
        self,
        portfolio_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_reconciliation_runs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_reconciliation_run(
        self,
        portfolio_id: str,
        run_id: str,
        as_of: datetime | None = None,
    ) -> Any | None: ...

    async def get_reconciliation_findings(
        self,
        run_id: str,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_reconciliation_findings_count(
        self,
        run_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_reconciliation_finding_summary(
        self,
        run_id: str,
        as_of: datetime | None = None,
    ) -> ReconciliationFindingSummary: ...

    async def get_portfolio_control_stages_count(
        self,
        portfolio_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_portfolio_control_stages(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_reprocessing_keys_count(
        self,
        portfolio_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_reprocessing_keys(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...

    async def get_reprocessing_jobs_count(
        self,
        portfolio_id: str,
        **filters: Any,
    ) -> int: ...

    async def get_reprocessing_jobs(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        **filters: Any,
    ) -> list[Any]: ...
