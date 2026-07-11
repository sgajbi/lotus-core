"""Tests for the remaining Query Service reference diagnostics facade."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.reconciliation_quality import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    STALE,
    UNRECONCILED,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.integration_service import (
    IntegrationService,
    IntegrationServiceDependencies,
)
from src.services.query_service.app.services.market_reference_coverage import (
    market_reference_coverage_response,
)
from src.services.query_service.app.services.reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)


def make_service() -> IntegrationService:
    return IntegrationService(AsyncMock(spec=AsyncSession))


def test_integration_service_accepts_explicit_repository_dependency() -> None:
    reference_repository = AsyncMock()

    service = IntegrationService(
        dependencies=IntegrationServiceDependencies(
            reference_repository=reference_repository,
        )
    )

    assert service.db is None
    assert service._reference_repository is reference_repository  # noqa: SLF001


def test_coverage_response_uses_exact_observed_dates() -> None:
    response = market_reference_coverage_response(
        coverage={
            "total_points": 6,
            "observed_start_date": date(2026, 1, 1),
            "observed_end_date": date(2026, 1, 3),
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 3)],
            "quality_status_counts": {"accepted": 6},
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.missing_dates_count == 1
    assert response.missing_dates_sample == [date(2026, 1, 2)]
    assert response.request_fingerprint == "fp-coverage-test"
    assert response.data_quality_status == PARTIAL


def test_coverage_response_bounds_missing_date_sample() -> None:
    response = market_reference_coverage_response(
        coverage={
            "total_points": 2,
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 20)],
            "quality_status_counts": {"accepted": 2},
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 20),
        request_fingerprint="fp-coverage-test",
    )

    assert response.missing_dates_count == 18
    assert response.missing_dates_sample == [date(2026, 1, day) for day in range(2, 12)]


@pytest.mark.parametrize(
    ("coverage", "expected_status"),
    [
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, day) for day in range(1, 4)],
                "quality_status_counts": {"accepted": 3},
            },
            COMPLETE,
        ),
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, day) for day in range(1, 4)],
                "quality_status_counts": {"STALE": 1, "accepted": 2},
            },
            STALE,
        ),
        (
            {"total_points": 0, "observed_dates": [], "quality_status_counts": {}},
            UNRECONCILED,
        ),
    ],
)
def test_coverage_response_classifies_quality(
    coverage: dict[str, object], expected_status: str
) -> None:
    response = market_reference_coverage_response(
        coverage=coverage,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.data_quality_status == expected_status


def test_coverage_response_carries_latest_evidence_timestamp() -> None:
    latest_evidence = datetime(2026, 1, 3, 14, 30, tzinfo=UTC)
    response = market_reference_coverage_response(
        coverage={
            "total_points": 3,
            "observed_dates": [date(2026, 1, day) for day in range(1, 4)],
            "quality_status_counts": {"accepted": 3},
            "latest_evidence_timestamp": latest_evidence,
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.latest_evidence_timestamp == latest_evidence


def test_market_reference_quality_classifies_partial_blocked_and_unknown() -> None:
    rows = [
        SimpleNamespace(quality_status="accepted"),
        SimpleNamespace(quality_status="estimated"),
        SimpleNamespace(quality_status="accepted"),
    ]

    assert market_reference_data_quality_status(rows, required_count=3) == PARTIAL
    assert (
        market_reference_data_quality_status(
            [SimpleNamespace(quality_status="blocked")], required_count=1
        )
        == BLOCKED
    )
    assert market_reference_data_quality_status([SimpleNamespace()], required_count=1) == "UNKNOWN"


def test_latest_reference_evidence_uses_durable_timestamps() -> None:
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)

    assert (
        latest_reference_evidence_timestamp(
            [
                SimpleNamespace(source_timestamp=older_source_timestamp),
                SimpleNamespace(updated_at=latest_updated_at),
            ]
        )
        == latest_updated_at
    )


@pytest.mark.asyncio
async def test_reference_diagnostics_delegate_to_repository() -> None:
    service = make_service()
    repository = SimpleNamespace(
        get_benchmark_coverage=AsyncMock(
            return_value={
                "total_points": 10,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 3),
                "quality_status_counts": {"accepted": 10},
            }
        ),
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 10,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 3),
                "quality_status_counts": {"accepted": 10},
            }
        ),
        list_taxonomy=AsyncMock(
            return_value=[
                SimpleNamespace(
                    classification_set_id="set1",
                    taxonomy_scope="index",
                    dimension_name="sector",
                    dimension_value="technology",
                    dimension_description="Technology",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
    )
    service._reference_repository = repository  # type: ignore[assignment]  # noqa: SLF001

    benchmark = await service.get_benchmark_coverage(
        "B1", date(2026, 1, 1), date(2026, 1, 3)
    )
    risk_free = await service.get_risk_free_coverage(
        "USD", date(2026, 1, 1), date(2026, 1, 3)
    )
    taxonomy = await service.get_classification_taxonomy(as_of_date=date(2026, 1, 1))

    assert benchmark.total_points == 10
    assert risk_free.total_points == 10
    assert taxonomy.records[0].dimension_name == "sector"
    assert benchmark.request_fingerprint
    assert risk_free.request_fingerprint
    assert taxonomy.request_fingerprint


@pytest.mark.asyncio
async def test_risk_free_coverage_normalizes_currency_before_repository_lookup() -> None:
    service = make_service()
    repository = SimpleNamespace(
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 1,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 1),
                "quality_status_counts": {"accepted": 1},
            }
        )
    )
    service._reference_repository = repository  # type: ignore[assignment]  # noqa: SLF001

    coverage = await service.get_risk_free_coverage(
        " usd ", date(2026, 1, 1), date(2026, 1, 1)
    )

    repository.get_risk_free_coverage.assert_awaited_once_with(
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )
    assert coverage.request_fingerprint
