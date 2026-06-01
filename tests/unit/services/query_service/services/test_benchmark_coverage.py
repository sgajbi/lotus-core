from datetime import UTC, date, datetime

from src.services.query_service.app.services.benchmark_coverage import (
    build_benchmark_coverage_response,
)


def test_build_benchmark_coverage_response_fingerprints_scope_and_maps_coverage() -> None:
    response = build_benchmark_coverage_response(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        coverage={
            "total_points": 2,
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 3)],
            "observed_start_date": date(2026, 1, 1),
            "observed_end_date": date(2026, 1, 3),
            "quality_status_counts": {"accepted": 2},
            "latest_evidence_timestamp": datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
        },
    )

    assert response.product_name == "DataQualityCoverageReport"
    assert response.request_fingerprint
    assert response.as_of_date == date(2026, 1, 3)
    assert response.expected_start_date == date(2026, 1, 1)
    assert response.expected_end_date == date(2026, 1, 3)
    assert response.total_points == 2
    assert response.missing_dates_count == 1
    assert response.missing_dates_sample == [date(2026, 1, 2)]
    assert response.quality_status_distribution == {"accepted": 2}
    assert response.data_quality_status == "PARTIAL"
    assert response.latest_evidence_timestamp == datetime(2026, 1, 3, 8, 0, tzinfo=UTC)


def test_build_benchmark_coverage_response_fingerprint_changes_by_benchmark() -> None:
    first = build_benchmark_coverage_response(
        benchmark_id="BMK_ONE",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        coverage={"observed_dates": [date(2026, 1, 1)], "quality_status_counts": {"accepted": 1}},
    )
    second = build_benchmark_coverage_response(
        benchmark_id="BMK_TWO",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        coverage={"observed_dates": [date(2026, 1, 1)], "quality_status_counts": {"accepted": 1}},
    )

    assert first.request_fingerprint != second.request_fingerprint
