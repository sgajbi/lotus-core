from datetime import date, datetime, timezone

from portfolio_common.observability_contracts import PORTFOLIO_SUPPORTABILITY_METRIC_LABELS

from src.services.query_service.app.dtos.operations_dto import SupportOverviewResponse
from src.services.query_service.app.repositories.operations_models import (
    MissingHistoricalFxDependencyRecord,
    MissingHistoricalFxDependencySummary,
    SnapshotValuationCoverageSummary,
)
from src.services.query_service.app.services.portfolio_readiness_builder import (
    PortfolioReadinessSnapshot,
    build_portfolio_readiness_response,
)


def _support_overview(**overrides: object) -> SupportOverviewResponse:
    defaults: dict[str, object] = {
        "portfolio_id": "P1",
        "business_date": date(2026, 5, 27),
        "current_epoch": 4,
        "stale_threshold_minutes": 15,
        "failed_window_hours": 24,
        "generated_at_utc": datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
        "active_reprocessing_keys": 0,
        "stale_reprocessing_keys": 0,
        "pending_valuation_jobs": 0,
        "processing_valuation_jobs": 0,
        "stale_processing_valuation_jobs": 0,
        "failed_valuation_jobs": 0,
        "failed_valuation_jobs_within_window": 0,
        "pending_aggregation_jobs": 0,
        "processing_aggregation_jobs": 0,
        "stale_processing_aggregation_jobs": 0,
        "failed_aggregation_jobs": 0,
        "failed_aggregation_jobs_within_window": 0,
        "pending_analytics_export_jobs": 0,
        "processing_analytics_export_jobs": 0,
        "stale_processing_analytics_export_jobs": 0,
        "failed_analytics_export_jobs": 0,
        "failed_analytics_export_jobs_within_window": 0,
        "latest_transaction_date": date(2026, 5, 27),
        "latest_booked_transaction_date": date(2026, 5, 27),
        "latest_position_snapshot_date": date(2026, 5, 27),
        "latest_booked_position_snapshot_date": date(2026, 5, 27),
        "position_snapshot_history_mismatch_count": 0,
        "controls_status": "COMPLETED",
        "controls_blocking": False,
        "publish_allowed": True,
    }
    defaults.update(overrides)
    return SupportOverviewResponse(**defaults)


def _snapshot(
    *,
    support_overview: SupportOverviewResponse | None = None,
    resolved_as_of_date: date | None = date(2026, 5, 27),
    latest_booked_transaction_date: date | None = date(2026, 5, 27),
    latest_booked_position_snapshot_date: date | None = date(2026, 5, 27),
    snapshot_coverage: SnapshotValuationCoverageSummary | None = None,
    missing_fx_summary: MissingHistoricalFxDependencySummary | None = None,
) -> PortfolioReadinessSnapshot:
    return PortfolioReadinessSnapshot(
        portfolio_id="P1",
        requested_as_of_date=resolved_as_of_date,
        resolved_as_of_date=resolved_as_of_date,
        generated_at_utc=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
        support_overview=support_overview or _support_overview(),
        latest_booked_transaction_date=latest_booked_transaction_date,
        latest_booked_position_snapshot_date=latest_booked_position_snapshot_date,
        snapshot_coverage=snapshot_coverage
        or SnapshotValuationCoverageSummary(
            snapshot_date=latest_booked_position_snapshot_date,
            total_positions=2,
            valued_positions=2,
            unvalued_positions=0,
        ),
        missing_fx_summary=missing_fx_summary
        or MissingHistoricalFxDependencySummary(
            missing_count=0,
            earliest_transaction_date=None,
            latest_transaction_date=None,
            sample_records=[],
        ),
    )


def test_build_portfolio_readiness_response_marks_ready_when_all_domains_clear():
    response = build_portfolio_readiness_response(_snapshot())

    assert response.holdings.status == "READY"
    assert response.pricing.status == "READY"
    assert response.transactions.status == "READY"
    assert response.reporting.status == "READY"
    assert response.blocking_reasons == []
    assert response.supportability.state == "ready"
    assert response.supportability.reason == "portfolio_supportability_ready"
    assert response.supportability.freshness_bucket == "current"
    assert response.supportability.metric_labels == PORTFOLIO_SUPPORTABILITY_METRIC_LABELS


def test_build_portfolio_readiness_response_marks_empty_without_activity():
    response = build_portfolio_readiness_response(
        _snapshot(
            resolved_as_of_date=None,
            latest_booked_transaction_date=None,
            latest_booked_position_snapshot_date=None,
            support_overview=_support_overview(
                business_date=None,
                latest_transaction_date=None,
                latest_booked_transaction_date=None,
                latest_position_snapshot_date=None,
                latest_booked_position_snapshot_date=None,
            ),
            snapshot_coverage=SnapshotValuationCoverageSummary(
                snapshot_date=None,
                total_positions=0,
                valued_positions=0,
                unvalued_positions=0,
            ),
        )
    )

    assert response.holdings.status == "NO_ACTIVITY"
    assert response.pricing.status == "NO_ACTIVITY"
    assert response.transactions.status == "NO_ACTIVITY"
    assert response.reporting.status == "NO_ACTIVITY"
    assert response.supportability.state == "empty"
    assert response.supportability.reason == "portfolio_supportability_empty"
    assert response.supportability.freshness_bucket == "unknown"


def test_build_portfolio_readiness_response_marks_pending_for_backlog_and_snapshot_lag():
    response = build_portfolio_readiness_response(
        _snapshot(
            support_overview=_support_overview(
                active_reprocessing_keys=1,
                pending_valuation_jobs=1,
                pending_aggregation_jobs=1,
                position_snapshot_history_mismatch_count=1,
                latest_booked_position_snapshot_date=date(2026, 5, 26),
            ),
            latest_booked_transaction_date=date(2026, 5, 27),
            latest_booked_position_snapshot_date=date(2026, 5, 26),
            snapshot_coverage=SnapshotValuationCoverageSummary(
                snapshot_date=date(2026, 5, 26),
                total_positions=3,
                valued_positions=2,
                unvalued_positions=1,
            ),
        )
    )

    assert response.holdings.status == "PENDING"
    assert response.pricing.status == "PENDING"
    assert response.transactions.status == "READY"
    assert response.reporting.status == "PENDING"
    assert response.supportability.state == "degraded"
    assert response.supportability.reason == "portfolio_supportability_pending"
    assert {reason.code for reason in response.holdings.reasons} == {
        "SNAPSHOT_BEHIND_TRANSACTION_LEDGER",
        "POSITION_HISTORY_SNAPSHOT_GAP",
        "REPROCESSING_KEYS_ACTIVE",
    }
    assert {reason.code for reason in response.pricing.reasons} == {
        "VALUATION_BACKLOG_OPEN",
        "UNVALUED_POSITIONS_REMAIN",
    }


def test_build_portfolio_readiness_response_ignores_future_pending_aggregation_for_as_of_date():
    response = build_portfolio_readiness_response(
        _snapshot(
            resolved_as_of_date=date(2026, 4, 10),
            support_overview=_support_overview(
                pending_aggregation_jobs=2,
                oldest_pending_aggregation_date=date(2026, 4, 17),
            ),
            latest_booked_transaction_date=date(2026, 4, 10),
            latest_booked_position_snapshot_date=date(2026, 4, 10),
            snapshot_coverage=SnapshotValuationCoverageSummary(
                snapshot_date=date(2026, 4, 10),
                total_positions=3,
                valued_positions=3,
                unvalued_positions=0,
            ),
        )
    )

    assert response.reporting.status == "READY"
    assert "AGGREGATION_BACKLOG_OPEN" not in {reason.code for reason in response.reporting.reasons}
    assert response.supportability.state == "ready"


def test_build_portfolio_readiness_response_marks_blocking_for_fx_and_controls():
    response = build_portfolio_readiness_response(
        _snapshot(
            support_overview=_support_overview(
                controls_status="REQUIRES_REPLAY",
                controls_blocking=True,
                publish_allowed=False,
                failed_valuation_jobs=1,
                failed_aggregation_jobs=1,
            ),
            missing_fx_summary=MissingHistoricalFxDependencySummary(
                missing_count=1,
                earliest_transaction_date=date(2026, 5, 20),
                latest_transaction_date=date(2026, 5, 20),
                sample_records=[
                    MissingHistoricalFxDependencyRecord(
                        transaction_id="TXN-1",
                        security_id="SEC-EUR-1",
                        transaction_date=date(2026, 5, 20),
                        trade_currency="EUR",
                        portfolio_currency="USD",
                    )
                ],
            ),
        )
    )

    assert response.holdings.status == "BLOCKED"
    assert response.pricing.status == "BLOCKED"
    assert response.transactions.status == "BLOCKED"
    assert response.reporting.status == "BLOCKED"
    assert response.supportability.state == "degraded"
    assert response.supportability.reason == "portfolio_supportability_blocked"
    assert response.publish_allowed is False
    assert response.missing_historical_fx_dependencies.missing_count == 1
    assert response.missing_historical_fx_dependencies.sample_records[0].transaction_id == "TXN-1"
    assert {reason.code for reason in response.blocking_reasons} >= {
        "MISSING_HISTORICAL_FX_PREREQUISITE",
        "VALUATION_JOBS_FAILED",
        "REPORTING_PUBLICATION_BLOCKED",
        "AGGREGATION_JOBS_FAILED",
    }
