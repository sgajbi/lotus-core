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

    if no_activity_domains == len(statuses):
        state = "empty"
        reason = "portfolio_supportability_empty"
    elif blocked_domains > 0:
        state = "degraded"
        reason = "portfolio_supportability_blocked"
    elif pending_domains > 0:
        state = "degraded"
        reason = "portfolio_supportability_pending"
    else:
        state = "ready"
        reason = "portfolio_supportability_ready"

    if resolved_as_of_date is None:
        freshness_bucket = "unknown"
    elif resolved_as_of_date >= generated_at_utc.date() - timedelta(days=1):
        freshness_bucket = "current"
    else:
        freshness_bucket = "stale"

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


def build_portfolio_readiness_response(
    snapshot: PortfolioReadinessSnapshot,
) -> PortfolioReadinessResponse:
    support_overview = snapshot.support_overview
    snapshot_coverage = snapshot.snapshot_coverage
    missing_fx_summary = snapshot.missing_fx_summary
    latest_booked_transaction_date = snapshot.latest_booked_transaction_date
    latest_booked_position_snapshot_date = snapshot.latest_booked_position_snapshot_date

    has_activity = (
        latest_booked_transaction_date is not None
        or latest_booked_position_snapshot_date is not None
    )

    holdings_reasons: list[PortfolioReadinessReason] = []
    pricing_reasons: list[PortfolioReadinessReason] = []
    transaction_reasons: list[PortfolioReadinessReason] = []
    reporting_reasons: list[PortfolioReadinessReason] = []

    if missing_fx_summary.missing_count > 0:
        transaction_reasons.append(
            _build_missing_fx_reason(domain="transactions", fx_summary=missing_fx_summary)
        )
        pricing_reasons.append(
            _build_missing_fx_reason(domain="pricing", fx_summary=missing_fx_summary)
        )
        reporting_reasons.append(
            _build_missing_fx_reason(domain="reporting", fx_summary=missing_fx_summary)
        )
        holdings_reasons.append(
            _build_missing_fx_reason(domain="holdings", fx_summary=missing_fx_summary)
        )

    if latest_booked_transaction_date is not None and (
        latest_booked_position_snapshot_date is None
        or latest_booked_position_snapshot_date < latest_booked_transaction_date
    ):
        holdings_reasons.append(
            _reason(
                code="SNAPSHOT_BEHIND_TRANSACTION_LEDGER",
                domain="holdings",
                severity="WARNING",
                message=(
                    "Current-epoch position snapshots lag the booked transaction ledger "
                    "for the resolved as-of date."
                ),
            )
        )

    if support_overview.position_snapshot_history_mismatch_count > 0:
        holdings_reasons.append(
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

    if support_overview.active_reprocessing_keys > 0:
        holdings_reasons.append(
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

    if support_overview.failed_valuation_jobs > 0:
        pricing_reasons.append(
            _reason(
                code="VALUATION_JOBS_FAILED",
                domain="pricing",
                severity="ERROR",
                message="One or more valuation jobs are in FAILED terminal state.",
            )
        )
    if support_overview.stale_processing_valuation_jobs > 0:
        pricing_reasons.append(
            _reason(
                code="VALUATION_JOBS_STALE",
                domain="pricing",
                severity="WARNING",
                message="One or more valuation jobs are stale in PROCESSING state.",
            )
        )
    if (
        support_overview.pending_valuation_jobs > 0
        or support_overview.processing_valuation_jobs > 0
    ):
        pricing_reasons.append(
            _reason(
                code="VALUATION_BACKLOG_OPEN",
                domain="pricing",
                severity="WARNING",
                message="Valuation work is still open for this portfolio.",
            )
        )
    if snapshot_coverage.unvalued_positions > 0:
        pricing_reasons.append(
            _reason(
                code="UNVALUED_POSITIONS_REMAIN",
                domain="pricing",
                severity="WARNING",
                message=(
                    "One or more current-epoch positions remain unvalued on the latest "
                    "booked snapshot date."
                ),
            )
        )

    if support_overview.controls_blocking:
        reporting_reasons.append(
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
        reporting_reasons.append(
            _reason(
                code="AGGREGATION_JOBS_FAILED",
                domain="reporting",
                severity="ERROR",
                message="One or more aggregation jobs are in FAILED terminal state.",
            )
        )
    if (
        support_overview.pending_aggregation_jobs > 0
        or support_overview.processing_aggregation_jobs > 0
        or support_overview.stale_processing_aggregation_jobs > 0
    ):
        reporting_reasons.append(
            _reason(
                code="AGGREGATION_BACKLOG_OPEN",
                domain="reporting",
                severity="WARNING",
                message="Aggregation work is still open for this portfolio.",
            )
        )

    if has_activity and holdings_reasons:
        reporting_reasons.append(
            _reason(
                code="HOLDINGS_COVERAGE_NOT_READY",
                domain="reporting",
                severity="WARNING",
                message="Holdings coverage is not yet fully ready for reporting consumption.",
            )
        )
    if has_activity and pricing_reasons:
        reporting_reasons.append(
            _reason(
                code="PRICING_COVERAGE_NOT_READY",
                domain="reporting",
                severity="WARNING",
                message="Pricing coverage is not yet fully ready for reporting consumption.",
            )
        )

    holdings = PortfolioReadinessBucket(
        status=_bucket_status(holdings_reasons, has_activity),
        reasons=holdings_reasons,
    )
    pricing = PortfolioReadinessBucket(
        status=_bucket_status(pricing_reasons, has_activity),
        reasons=pricing_reasons,
    )
    transactions = PortfolioReadinessBucket(
        status=_bucket_status(
            transaction_reasons,
            latest_booked_transaction_date is not None,
        ),
        reasons=transaction_reasons,
    )
    reporting = PortfolioReadinessBucket(
        status=_bucket_status(reporting_reasons, has_activity),
        reasons=reporting_reasons,
    )
    supportability = _portfolio_supportability_summary(
        buckets=[holdings, pricing, transactions, reporting],
        resolved_as_of_date=snapshot.resolved_as_of_date,
        generated_at_utc=snapshot.generated_at_utc,
    )

    return PortfolioReadinessResponse(
        portfolio_id=snapshot.portfolio_id,
        requested_as_of_date=snapshot.requested_as_of_date,
        resolved_as_of_date=snapshot.resolved_as_of_date,
        generated_at_utc=snapshot.generated_at_utc,
        holdings=holdings,
        pricing=pricing,
        transactions=transactions,
        reporting=reporting,
        blocking_reasons=(
            _blocking_reasons(holdings_reasons)
            + _blocking_reasons(pricing_reasons)
            + _blocking_reasons(transaction_reasons)
            + _blocking_reasons(reporting_reasons)
        ),
        supportability=supportability,
        latest_booked_transaction_date=latest_booked_transaction_date,
        latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
        current_epoch=support_overview.current_epoch,
        position_snapshot_history_mismatch_count=(
            support_overview.position_snapshot_history_mismatch_count
        ),
        snapshot_valuation_total_positions=snapshot_coverage.total_positions,
        snapshot_valuation_valued_positions=snapshot_coverage.valued_positions,
        snapshot_valuation_unvalued_positions=snapshot_coverage.unvalued_positions,
        controls_status=support_overview.controls_status,
        publish_allowed=support_overview.publish_allowed,
        missing_historical_fx_dependencies={
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
        },
    )
