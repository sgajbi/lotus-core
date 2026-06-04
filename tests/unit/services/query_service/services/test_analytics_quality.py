from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL

from src.services.query_service.app.services.analytics_quality import (
    bounded_latest_performance_date,
    latest_portfolio_horizon_candidate,
    latest_position_horizon_with_observations,
    portfolio_reference_data_quality_status,
    portfolio_reference_evidence_timestamp,
    quality_status_from_epoch,
    timeseries_data_quality_status,
)


def test_quality_status_from_epoch_classifies_current_and_restated_rows() -> None:
    assert quality_status_from_epoch(0) == "final"
    assert quality_status_from_epoch(2) == "restated"


def test_timeseries_data_quality_status_classifies_empty_and_missing_windows() -> None:
    assert (
        timeseries_data_quality_status(required_count=0, observed_count=0, stale_count=0)
        == "UNKNOWN"
    )
    assert (
        timeseries_data_quality_status(required_count=3, observed_count=2, stale_count=0)
        == "PARTIAL"
    )


def test_portfolio_reference_quality_status_depends_on_performance_date() -> None:
    assert (
        portfolio_reference_data_quality_status(performance_end_date=date(2025, 1, 31)) == COMPLETE
    )
    assert portfolio_reference_data_quality_status(performance_end_date=None) == PARTIAL


def test_portfolio_reference_evidence_timestamp_uses_latest_available_timestamp() -> None:
    created_at = datetime(2025, 1, 1, tzinfo=UTC)
    source_timestamp = datetime(2025, 1, 3, tzinfo=UTC)
    updated_at = datetime(2025, 1, 2, tzinfo=UTC)

    assert (
        portfolio_reference_evidence_timestamp(
            SimpleNamespace(
                created_at=created_at,
                updated_at=updated_at,
                source_timestamp=source_timestamp,
            )
        )
        == source_timestamp
    )


def test_latest_horizon_helpers_include_observed_position_dates_and_as_of_bound() -> None:
    observed_dates = [date(2025, 1, 30), date(2025, 2, 3)]

    assert latest_position_horizon_with_observations(
        latest_position_date=date(2025, 1, 31),
        observed_dates=observed_dates,
    ) == date(2025, 2, 3)
    assert latest_portfolio_horizon_candidate(
        latest_portfolio_date=date(2025, 1, 29),
        observed_dates=observed_dates,
    ) == date(2025, 2, 3)
    assert bounded_latest_performance_date(
        portfolio_candidate=date(2025, 2, 3),
        latest_position_date=date(2025, 2, 4),
        as_of_date=date(2025, 2, 2),
    ) == date(2025, 2, 2)
