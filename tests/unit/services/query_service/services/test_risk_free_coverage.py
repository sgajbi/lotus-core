from datetime import UTC, date, datetime

from src.services.query_service.app.services.risk_free_coverage import (
    build_risk_free_coverage_response,
)


def test_build_risk_free_coverage_response_fingerprints_currency_scope() -> None:
    response = build_risk_free_coverage_response(
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        coverage={
            "total_points": 2,
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 2)],
            "observed_start_date": date(2026, 1, 1),
            "observed_end_date": date(2026, 1, 2),
            "quality_status_counts": {"accepted": 2},
            "latest_evidence_timestamp": datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
        },
    )

    assert response.product_name == "DataQualityCoverageReport"
    assert response.request_fingerprint
    assert response.as_of_date == date(2026, 1, 2)
    assert response.expected_start_date == date(2026, 1, 1)
    assert response.expected_end_date == date(2026, 1, 2)
    assert response.total_points == 2
    assert response.missing_dates_count == 0
    assert response.missing_dates_sample == []
    assert response.quality_status_distribution == {"accepted": 2}
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


def test_build_risk_free_coverage_response_fingerprint_changes_by_currency() -> None:
    first = build_risk_free_coverage_response(
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        coverage={"observed_dates": [date(2026, 1, 1)], "quality_status_counts": {"accepted": 1}},
    )
    second = build_risk_free_coverage_response(
        currency="SGD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        coverage={"observed_dates": [date(2026, 1, 1)], "quality_status_counts": {"accepted": 1}},
    )

    assert first.request_fingerprint != second.request_fingerprint
