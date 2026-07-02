from dataclasses import dataclass
from datetime import date, datetime, timedelta

from portfolio_common.monitoring import observe_portfolio_supportability

from ..dtos.operations_dto import (
    PortfolioReadinessBucket,
    PortfolioReadinessReason,
    PortfolioReadinessResponse,
    PortfolioSupportabilitySummary,
    SupportOverviewResponse,
)
from ..repositories.operations_models import (
    MissingHistoricalFxDependencySummary as RepositoryMissingHistoricalFxDependencySummary,
)
from ..repositories.operations_models import (
    SnapshotValuationCoverageSummary,
)


@dataclass(frozen=True)
class PortfolioReadinessSnapshot:
    portfolio_id: str
    requested_as_of_date: date | None
    resolved_as_of_date: date | None
    generated_at_utc: datetime
    support_overview: SupportOverviewResponse
    latest_booked_transaction_date: date | None
    latest_booked_position_snapshot_date: date | None
    snapshot_coverage: SnapshotValuationCoverageSummary
    missing_fx_summary: RepositoryMissingHistoricalFxDependencySummary


@dataclass(frozen=True)
class _PortfolioReadinessReasons:
    holdings: list[PortfolioReadinessReason]
    pricing: list[PortfolioReadinessReason]
    transactions: list[PortfolioReadinessReason]
    reporting: list[PortfolioReadinessReason]


@dataclass(frozen=True)
class _PortfolioReadinessBuckets:
    holdings: PortfolioReadinessBucket
    pricing: PortfolioReadinessBucket
    transactions: PortfolioReadinessBucket
    reporting: PortfolioReadinessBucket


def _reason(
    *,
    code: str,
    domain: str,
    severity: str,
    message: str,
    affected_transaction_ids: list[str] | None = None,
    affected_security_ids: list[str] | None = None,
) -> PortfolioReadinessReason:
    return PortfolioReadinessReason(
        code=code,
        domain=domain,
        severity=severity,
        message=message,
        affected_transaction_ids=affected_transaction_ids or [],
        affected_security_ids=affected_security_ids or [],
    )


def _bucket_status(reasons: list[PortfolioReadinessReason], has_activity: bool) -> str:
    if not has_activity:
        return "NO_ACTIVITY"
    if any(reason.severity == "ERROR" for reason in reasons):
        return "BLOCKED"
    if reasons:
        return "PENDING"
    return "READY"


def _supportability_state_reason(
    *,
    total_domains: int,
    no_activity_domains: int,
    blocked_domains: int,
    pending_domains: int,
) -> tuple[str, str]:
    if no_activity_domains == total_domains:
        return "empty", "portfolio_supportability_empty"
    if blocked_domains > 0:
        return "degraded", "portfolio_supportability_blocked"
    if pending_domains > 0:
        return "degraded", "portfolio_supportability_pending"
    return "ready", "portfolio_supportability_ready"


def _supportability_freshness_bucket(
    *,
    resolved_as_of_date: date | None,
    generated_at_utc: datetime,
) -> str:
    if resolved_as_of_date is None:
        return "unknown"
    if resolved_as_of_date >= generated_at_utc.date() - timedelta(days=1):
        return "current"
    return "stale"


def _portfolio_supportability_summary(
    *,
    buckets: list[PortfolioReadinessBucket],
    resolved_as_of_date: date | None,
    generated_at_utc: datetime,
) -> PortfolioSupportabilitySummary:
    statuses = [bucket.status for bucket in buckets]
    ready_domains = statuses.count("READY")
    pending_domains = statuses.count("PENDING")
    blocked_domains = statuses.count("BLOCKED")
    no_activity_domains = statuses.count("NO_ACTIVITY")

    state, reason = _supportability_state_reason(
        total_domains=len(statuses),
        no_activity_domains=no_activity_domains,
        blocked_domains=blocked_domains,
        pending_domains=pending_domains,
    )
    freshness_bucket = _supportability_freshness_bucket(
        resolved_as_of_date=resolved_as_of_date,
        generated_at_utc=generated_at_utc,
    )

    observe_portfolio_supportability(state, reason, freshness_bucket)
    return PortfolioSupportabilitySummary(
        state=state,
        reason=reason,
        freshness_bucket=freshness_bucket,
        ready_domains=ready_domains,
        pending_domains=pending_domains,
        blocked_domains=blocked_domains,
        no_activity_domains=no_activity_domains,
    )


def _blocking_reasons(
    reasons: list[PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    return [reason for reason in reasons if reason.severity == "ERROR"]


def _build_missing_fx_reason(
    *,
    domain: str,
    fx_summary: RepositoryMissingHistoricalFxDependencySummary,
) -> PortfolioReadinessReason:
    return _reason(
        code="MISSING_HISTORICAL_FX_PREREQUISITE",
        domain=domain,
        severity="ERROR",
        message=(
            "Cross-currency transactions are missing historical FX prerequisites "
            "required for complete source-owned coverage."
        ),
        affected_transaction_ids=[record.transaction_id for record in fx_summary.sample_records],
        affected_security_ids=sorted(
            {record.security_id for record in fx_summary.sample_records if record.security_id}
        ),
    )


def _has_portfolio_activity(snapshot: PortfolioReadinessSnapshot) -> bool:
    return (
        snapshot.latest_booked_transaction_date is not None
        or snapshot.latest_booked_position_snapshot_date is not None
    )


def _missing_fx_reasons(
    missing_fx_summary: RepositoryMissingHistoricalFxDependencySummary,
) -> dict[str, PortfolioReadinessReason]:
    if missing_fx_summary.missing_count <= 0:
        return {}
    return {
        domain: _build_missing_fx_reason(domain=domain, fx_summary=missing_fx_summary)
        for domain in ("transactions", "pricing", "reporting", "holdings")
    }


def _snapshot_lag_reason(
    snapshot: PortfolioReadinessSnapshot,
) -> PortfolioReadinessReason | None:
    latest_transaction_date = snapshot.latest_booked_transaction_date
    latest_snapshot_date = snapshot.latest_booked_position_snapshot_date
    if latest_transaction_date is None:
        return None
    if latest_snapshot_date is not None and latest_snapshot_date >= latest_transaction_date:
        return None
    return _reason(
        code="SNAPSHOT_BEHIND_TRANSACTION_LEDGER",
        domain="holdings",
        severity="WARNING",
        message=(
            "Current-epoch position snapshots lag the booked transaction ledger "
            "for the resolved as-of date."
        ),
    )


def _holdings_reasons(
    *,
    snapshot: PortfolioReadinessSnapshot,
    missing_fx_reasons: dict[str, PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    reasons = []
    if missing_fx_reason := missing_fx_reasons.get("holdings"):
        reasons.append(missing_fx_reason)
    if snapshot_lag_reason := _snapshot_lag_reason(snapshot):
        reasons.append(snapshot_lag_reason)
    if snapshot.support_overview.position_snapshot_history_mismatch_count > 0:
        reasons.append(
            _reason(
                code="POSITION_HISTORY_SNAPSHOT_GAP",
                domain="holdings",
                severity="WARNING",
                message=(
                    "Position history exists without matching current-epoch daily snapshots "
                    "for one or more keys."
                ),
            )
        )
    if snapshot.support_overview.active_reprocessing_keys > 0:
        reasons.append(
            _reason(
                code="REPROCESSING_KEYS_ACTIVE",
                domain="holdings",
                severity="WARNING",
                message=(
                    "Replay keys are still active for this portfolio, so holdings coverage "
                    "may still be converging."
                ),
            )
        )
    return reasons


def _valuation_job_reasons(
    support_overview: SupportOverviewResponse,
) -> list[PortfolioReadinessReason]:
    reasons = []
    if support_overview.failed_valuation_jobs > 0:
        reasons.append(
            _reason(
                code="VALUATION_JOBS_FAILED",
                domain="pricing",
                severity="ERROR",
                message="One or more valuation jobs are in FAILED terminal state.",
            )
        )
    if support_overview.stale_processing_valuation_jobs > 0:
        reasons.append(
            _reason(
                code="VALUATION_JOBS_STALE",
                domain="pricing",
                severity="WARNING",
                message="One or more valuation jobs are stale in PROCESSING state.",
            )
        )
    return reasons


def _valuation_backlog_reason(
    support_overview: SupportOverviewResponse,
) -> PortfolioReadinessReason | None:
    if support_overview.pending_valuation_jobs <= 0 and not (
        support_overview.processing_valuation_jobs
    ):
        return None
    return _reason(
        code="VALUATION_BACKLOG_OPEN",
        domain="pricing",
        severity="WARNING",
        message="Valuation work is still open for this portfolio.",
    )


def _unvalued_positions_reason(
    snapshot_coverage: SnapshotValuationCoverageSummary,
) -> PortfolioReadinessReason | None:
    if snapshot_coverage.unvalued_positions <= 0:
        return None
    return _reason(
        code="UNVALUED_POSITIONS_REMAIN",
        domain="pricing",
        severity="WARNING",
        message=(
            "One or more current-epoch positions remain unvalued on the latest "
            "booked snapshot date."
        ),
    )


def _pricing_reasons(
    *,
    snapshot: PortfolioReadinessSnapshot,
    missing_fx_reasons: dict[str, PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    reasons = []
    if missing_fx_reason := missing_fx_reasons.get("pricing"):
        reasons.append(missing_fx_reason)
    reasons.extend(_valuation_job_reasons(snapshot.support_overview))
    if backlog_reason := _valuation_backlog_reason(snapshot.support_overview):
        reasons.append(backlog_reason)
    if unvalued_reason := _unvalued_positions_reason(snapshot.snapshot_coverage):
        reasons.append(unvalued_reason)
    return reasons


def _transaction_reasons(
    missing_fx_reasons: dict[str, PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    if missing_fx_reason := missing_fx_reasons.get("transactions"):
        return [missing_fx_reason]
    return []


def _reporting_control_reasons(
    support_overview: SupportOverviewResponse,
) -> list[PortfolioReadinessReason]:
    reasons = []
    if support_overview.controls_blocking:
        reasons.append(
            _reason(
                code="REPORTING_PUBLICATION_BLOCKED",
                domain="reporting",
                severity="ERROR",
                message=(
                    "Financial reconciliation controls are blocking downstream reporting "
                    "publication for the portfolio."
                ),
            )
        )
    if support_overview.failed_aggregation_jobs > 0:
        reasons.append(
            _reason(
                code="AGGREGATION_JOBS_FAILED",
                domain="reporting",
                severity="ERROR",
                message="One or more aggregation jobs are in FAILED terminal state.",
            )
        )
    return reasons


def _reporting_backlog_reason(
    support_overview: SupportOverviewResponse,
    resolved_as_of_date: date | None,
) -> PortfolioReadinessReason | None:
    pending_jobs = support_overview.pending_aggregation_jobs
    processing_jobs = support_overview.processing_aggregation_jobs
    stale_processing_jobs = support_overview.stale_processing_aggregation_jobs
    oldest_pending_date = support_overview.oldest_pending_aggregation_date
    if (
        pending_jobs > 0
        and resolved_as_of_date is not None
        and oldest_pending_date is not None
        and oldest_pending_date > resolved_as_of_date
    ):
        pending_jobs = 0
        processing_jobs = 0
        stale_processing_jobs = 0

    if pending_jobs > 0 or processing_jobs > 0 or stale_processing_jobs > 0:
        return _reason(
            code="AGGREGATION_BACKLOG_OPEN",
            domain="reporting",
            severity="WARNING",
            message="Aggregation work is still open for this portfolio.",
        )
    return None


def _reporting_dependency_reasons(
    *,
    has_activity: bool,
    holdings_reasons: list[PortfolioReadinessReason],
    pricing_reasons: list[PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    reasons = []
    if has_activity and holdings_reasons:
        reasons.append(
            _reason(
                code="HOLDINGS_COVERAGE_NOT_READY",
                domain="reporting",
                severity="WARNING",
                message="Holdings coverage is not yet fully ready for reporting consumption.",
            )
        )
    if has_activity and pricing_reasons:
        reasons.append(
            _reason(
                code="PRICING_COVERAGE_NOT_READY",
                domain="reporting",
                severity="WARNING",
                message="Pricing coverage is not yet fully ready for reporting consumption.",
            )
        )
    return reasons


def _reporting_reasons(
    *,
    snapshot: PortfolioReadinessSnapshot,
    has_activity: bool,
    holdings_reasons: list[PortfolioReadinessReason],
    pricing_reasons: list[PortfolioReadinessReason],
    missing_fx_reasons: dict[str, PortfolioReadinessReason],
) -> list[PortfolioReadinessReason]:
    reasons = []
    if missing_fx_reason := missing_fx_reasons.get("reporting"):
        reasons.append(missing_fx_reason)
    reasons.extend(_reporting_control_reasons(snapshot.support_overview))
    if backlog_reason := _reporting_backlog_reason(
        snapshot.support_overview,
        snapshot.resolved_as_of_date,
    ):
        reasons.append(backlog_reason)
    reasons.extend(
        _reporting_dependency_reasons(
            has_activity=has_activity,
            holdings_reasons=holdings_reasons,
            pricing_reasons=pricing_reasons,
        )
    )
    return reasons


def _portfolio_readiness_reasons(
    snapshot: PortfolioReadinessSnapshot,
    *,
    has_activity: bool,
) -> _PortfolioReadinessReasons:
    missing_fx_reasons = _missing_fx_reasons(snapshot.missing_fx_summary)
    holdings = _holdings_reasons(snapshot=snapshot, missing_fx_reasons=missing_fx_reasons)
    pricing = _pricing_reasons(snapshot=snapshot, missing_fx_reasons=missing_fx_reasons)
    return _PortfolioReadinessReasons(
        holdings=holdings,
        pricing=pricing,
        transactions=_transaction_reasons(missing_fx_reasons),
        reporting=_reporting_reasons(
            snapshot=snapshot,
            has_activity=has_activity,
            holdings_reasons=holdings,
            pricing_reasons=pricing,
            missing_fx_reasons=missing_fx_reasons,
        ),
    )


def _portfolio_readiness_buckets(
    *,
    reasons: _PortfolioReadinessReasons,
    has_activity: bool,
    has_transactions: bool,
) -> _PortfolioReadinessBuckets:
    holdings = PortfolioReadinessBucket(
        status=_bucket_status(reasons.holdings, has_activity),
        reasons=reasons.holdings,
    )
    pricing = PortfolioReadinessBucket(
        status=_bucket_status(reasons.pricing, has_activity),
        reasons=reasons.pricing,
    )
    transactions = PortfolioReadinessBucket(
        status=_bucket_status(reasons.transactions, has_transactions),
        reasons=reasons.transactions,
    )
    reporting = PortfolioReadinessBucket(
        status=_bucket_status(reasons.reporting, has_activity),
        reasons=reasons.reporting,
    )
    return _PortfolioReadinessBuckets(
        holdings=holdings,
        pricing=pricing,
        transactions=transactions,
        reporting=reporting,
    )


def _blocking_reasons_from_groups(
    reasons: _PortfolioReadinessReasons,
) -> list[PortfolioReadinessReason]:
    return (
        _blocking_reasons(reasons.holdings)
        + _blocking_reasons(reasons.pricing)
        + _blocking_reasons(reasons.transactions)
        + _blocking_reasons(reasons.reporting)
    )


def _missing_historical_fx_dependencies_payload(
    missing_fx_summary: RepositoryMissingHistoricalFxDependencySummary,
) -> dict[str, object]:
    return {
        "missing_count": missing_fx_summary.missing_count,
        "earliest_transaction_date": missing_fx_summary.earliest_transaction_date,
        "latest_transaction_date": missing_fx_summary.latest_transaction_date,
        "sample_records": [
            {
                "transaction_id": record.transaction_id,
                "security_id": record.security_id,
                "transaction_date": record.transaction_date,
                "trade_currency": record.trade_currency,
                "portfolio_currency": record.portfolio_currency,
            }
            for record in missing_fx_summary.sample_records
        ],
    }


def build_portfolio_readiness_response(
    snapshot: PortfolioReadinessSnapshot,
) -> PortfolioReadinessResponse:
    has_activity = _has_portfolio_activity(snapshot)
    reasons = _portfolio_readiness_reasons(snapshot, has_activity=has_activity)
    buckets = _portfolio_readiness_buckets(
        reasons=reasons,
        has_activity=has_activity,
        has_transactions=snapshot.latest_booked_transaction_date is not None,
    )
    supportability = _portfolio_supportability_summary(
        buckets=[
            buckets.holdings,
            buckets.pricing,
            buckets.transactions,
            buckets.reporting,
        ],
        resolved_as_of_date=snapshot.resolved_as_of_date,
        generated_at_utc=snapshot.generated_at_utc,
    )

    return PortfolioReadinessResponse(
        portfolio_id=snapshot.portfolio_id,
        requested_as_of_date=snapshot.requested_as_of_date,
        resolved_as_of_date=snapshot.resolved_as_of_date,
        generated_at_utc=snapshot.generated_at_utc,
        holdings=buckets.holdings,
        pricing=buckets.pricing,
        transactions=buckets.transactions,
        reporting=buckets.reporting,
        blocking_reasons=_blocking_reasons_from_groups(reasons),
        supportability=supportability,
        latest_booked_transaction_date=snapshot.latest_booked_transaction_date,
        latest_booked_position_snapshot_date=snapshot.latest_booked_position_snapshot_date,
        current_epoch=snapshot.support_overview.current_epoch,
        position_snapshot_history_mismatch_count=(
            snapshot.support_overview.position_snapshot_history_mismatch_count
        ),
        snapshot_valuation_total_positions=snapshot.snapshot_coverage.total_positions,
        snapshot_valuation_valued_positions=snapshot.snapshot_coverage.valued_positions,
        snapshot_valuation_unvalued_positions=snapshot.snapshot_coverage.unvalued_positions,
        controls_status=snapshot.support_overview.controls_status,
        publish_allowed=snapshot.support_overview.publish_allowed,
        missing_historical_fx_dependencies=_missing_historical_fx_dependencies_payload(
            snapshot.missing_fx_summary
        ),
    )
