from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE, PARTIAL, STALE, UNRECONCILED
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


def test_integration_service_accepts_explicit_dependencies_without_session() -> None:
    reference_repository = AsyncMock()
    page_token_codec = SimpleNamespace(
        encode=lambda payload: f"encoded:{payload['scope']}",
        decode=lambda token: {"token": token},
    )

    service = IntegrationService(
        dependencies=IntegrationServiceDependencies(
            reference_repository=reference_repository,
            page_token_codec=page_token_codec,
        )
    )

    assert service.db is None
    assert service._reference_repository is reference_repository  # pylint: disable=protected-access
    assert service._encode_page_token({"scope": "benchmark"}) == "encoded:benchmark"
    assert service._decode_page_token("token-1") == {"token": "token-1"}


def profile_binding_row(as_of_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        effective_from=as_of_date,
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def test_to_coverage_response_uses_exact_observed_dates_when_present() -> None:
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


def test_to_coverage_response_streams_missing_date_sample_for_broad_windows() -> None:
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
    assert response.missing_dates_sample == [
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 4),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 10),
        date(2026, 1, 11),
    ]


@pytest.mark.parametrize(
    ("coverage", "expected_status"),
    [
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
                "quality_status_counts": {"accepted": 3},
            },
            COMPLETE,
        ),
        (
            {
                "total_points": 3,
                "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
                "quality_status_counts": {"STALE": 1, "accepted": 2},
            },
            STALE,
        ),
        (
            {
                "total_points": 0,
                "observed_dates": [],
                "quality_status_counts": {},
            },
            UNRECONCILED,
        ),
    ],
)
def test_to_coverage_response_classifies_data_quality_status(
    coverage: dict[str, object],
    expected_status: str,
) -> None:
    response = market_reference_coverage_response(
        coverage=coverage,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.data_quality_status == expected_status


def test_to_coverage_response_carries_latest_evidence_timestamp() -> None:
    latest_evidence_timestamp = datetime(2026, 1, 3, 14, 30, tzinfo=UTC)

    response = market_reference_coverage_response(
        coverage={
            "total_points": 3,
            "observed_dates": [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
            "quality_status_counts": {"accepted": 3},
            "latest_evidence_timestamp": latest_evidence_timestamp,
        },
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.latest_evidence_timestamp == latest_evidence_timestamp


def test_market_reference_data_quality_classifies_reference_rows() -> None:
    rows = [
        SimpleNamespace(quality_status="accepted"),
        SimpleNamespace(quality_status="estimated"),
        SimpleNamespace(quality_status="accepted"),
    ]

    assert (
        market_reference_data_quality_status(
            rows,
            required_count=len(rows),
        )
        == PARTIAL
    )
    assert (
        market_reference_data_quality_status(
            [SimpleNamespace(quality_status="blocked")],
            required_count=1,
        )
        == BLOCKED
    )
    assert (
        market_reference_data_quality_status(
            [SimpleNamespace()],
            required_count=1,
        )
        == "UNKNOWN"
    )


def test_latest_reference_evidence_timestamp_uses_durable_reference_timestamps() -> None:
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
async def test_reference_contract_methods() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(
            return_value=SimpleNamespace(
                benchmark_id="B1",
                benchmark_name="Benchmark 1",
                benchmark_type="composite",
                benchmark_currency="USD",
                return_convention="total_return_index",
                benchmark_status="active",
                benchmark_family="family",
                benchmark_provider="provider",
                rebalance_frequency="monthly",
                classification_set_id="set1",
                classification_labels={"asset_class": "equity"},
                effective_from=date(2026, 1, 1),
                effective_to=None,
                quality_status="accepted",
                source_timestamp=None,
                source_vendor="vendor",
                source_record_id="src1",
            )
        ),
        list_benchmark_definitions_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    benchmark_id="B1",
                    benchmark_currency="USD",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_components=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                    rebalance_event_id="r1",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 3, 31),
                    rebalance_event_id="r1",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(return_value=["IDX1"]),
        list_benchmark_components_for_benchmarks=AsyncMock(
            return_value={
                "B1": [
                    SimpleNamespace(
                        index_id="IDX1",
                        composition_weight=Decimal("0.5"),
                        composition_effective_from=date(2026, 1, 1),
                        composition_effective_to=None,
                        rebalance_event_id="r1",
                        quality_status="accepted",
                    )
                ]
            }
        ),
        list_benchmark_definitions=AsyncMock(return_value=[]),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        list_index_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.008"),
                    return_period="1d",
                    return_convention="total_return_index",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        get_fx_rates=AsyncMock(return_value={date(2026, 1, 1): Decimal("1.1")}),
        list_risk_free_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    value=Decimal("0.03"),
                    value_convention="annualized_rate",
                    day_count_convention="act_360",
                    compounding_convention="simple",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
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
                    dimension_description="desc",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
    )

    market_series = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "index_return", "benchmark_return", "component_weight"],
        ),
    )
    assert market_series.component_series
    assert market_series.benchmark_currency == "USD"
    assert market_series.target_currency == "USD"
    assert (
        market_series.normalization_status
        == "native_component_series_with_identity_benchmark_to_target_fx_context"
    )
    assert (
        market_series.normalization_policy
        == "native_component_series_downstream_normalization_required"
    )
    assert market_series.component_series[0].points[0].series_currency == "USD"
    assert market_series.request_fingerprint
    assert market_series.page.page_size == 250
    assert market_series.page.sort_key == "index_id:asc"
    assert market_series.page.returned_component_count == 1
    assert market_series.page.request_scope_fingerprint == market_series.request_fingerprint
    assert market_series.page.next_page_token is None
    assert market_series.product_name == "MarketDataWindow"
    assert market_series.as_of_date == date(2026, 1, 1)
    assert market_series.reconciliation_status == "UNKNOWN"
    assert market_series.data_quality_status == COMPLETE

    benchmark_return = await service.get_benchmark_return_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert benchmark_return.points
    assert benchmark_return.as_of_date == date(2026, 1, 1)
    assert benchmark_return.request_fingerprint

    risk_free = await service.get_risk_free_series(
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            currency="USD",
            series_mode="annualized_rate_series",
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert risk_free.points
    assert risk_free.as_of_date == date(2026, 1, 1)
    assert risk_free.request_fingerprint
    assert risk_free.product_name == "RiskFreeSeriesWindow"

    coverage = await service.get_benchmark_coverage("B1", date(2026, 1, 1), date(2026, 1, 3))
    assert coverage.total_points == 10
    assert coverage.request_fingerprint
    assert coverage.product_name == "DataQualityCoverageReport"
    assert coverage.as_of_date == date(2026, 1, 3)

    rf_coverage = await service.get_risk_free_coverage("USD", date(2026, 1, 1), date(2026, 1, 3))
    assert rf_coverage.total_points == 10
    assert rf_coverage.request_fingerprint
    assert rf_coverage.product_name == "DataQualityCoverageReport"
    assert rf_coverage.as_of_date == date(2026, 1, 3)

    taxonomy = await service.get_classification_taxonomy(as_of_date=date(2026, 1, 1))
    assert taxonomy.records[0].dimension_name == "sector"
    assert taxonomy.request_fingerprint
    assert taxonomy.product_name == "InstrumentReferenceBundle"
    assert taxonomy.restatement_version == "current"


@pytest.mark.asyncio
async def test_risk_free_products_normalize_currency_before_repository_lookup() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment] # pylint: disable=protected-access
        list_risk_free_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    value=Decimal("0.03"),
                    value_convention="annualized_rate",
                    day_count_convention="act_360",
                    compounding_convention="simple",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 1,
                "observed_start_date": date(2026, 1, 1),
                "observed_end_date": date(2026, 1, 1),
                "quality_status_counts": {"accepted": 1},
            }
        ),
    )

    risk_free = await service.get_risk_free_series(
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            currency=" usd ",
            series_mode="annualized_rate_series",
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
        ),
    )
    coverage = await service.get_risk_free_coverage(" usd ", date(2026, 1, 1), date(2026, 1, 1))

    service._reference_repository.list_risk_free_series.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=protected-access
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )
    service._reference_repository.get_risk_free_coverage.assert_awaited_once_with(  # type: ignore[attr-defined] # pylint: disable=protected-access
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )
    assert risk_free.currency == "USD"
    assert risk_free.request_fingerprint
    assert coverage.request_fingerprint


@pytest.mark.asyncio
async def test_reference_contract_none_and_fx_branches() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(
            side_effect=[
                SimpleNamespace(benchmark_currency="EUR"),
                SimpleNamespace(benchmark_currency="EUR"),
            ]
        ),
        list_benchmark_definitions_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_components=AsyncMock(return_value=[]),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_components_for_benchmarks=AsyncMock(return_value={}),
        list_benchmark_definitions=AsyncMock(
            return_value=[
                SimpleNamespace(
                    benchmark_id="B1",
                    benchmark_name="Benchmark 1",
                    benchmark_type="single_index",
                    benchmark_currency="EUR",
                    return_convention="total_return_index",
                    benchmark_status="active",
                    benchmark_family=None,
                    benchmark_provider=None,
                    rebalance_frequency=None,
                    classification_set_id=None,
                    classification_labels={},
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                    source_timestamp=None,
                    source_vendor=None,
                    source_record_id=None,
                )
            ]
        ),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
        list_risk_free_series=AsyncMock(return_value=[]),
        get_benchmark_coverage=AsyncMock(
            return_value={
                "total_points": 0,
                "observed_start_date": None,
                "observed_end_date": None,
                "quality_status_counts": {},
            }
        ),
        get_risk_free_coverage=AsyncMock(
            return_value={
                "total_points": 0,
                "observed_start_date": None,
                "observed_end_date": None,
                "quality_status_counts": {},
            }
        ),
        list_taxonomy=AsyncMock(return_value=[]),
    )

    await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "fx_rate"],
        ),
    )
    service._reference_repository.get_fx_rates.assert_awaited_once()
    benchmark_market_series = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price"],
        ),
    )
    assert benchmark_market_series.benchmark_currency == "EUR"
    assert benchmark_market_series.target_currency == "USD"
    assert (
        benchmark_market_series.normalization_status
        == "native_component_series_without_fx_context_request"
    )
    assert benchmark_market_series.fx_context_source_currency == "EUR"
    assert benchmark_market_series.fx_context_target_currency == "USD"


@pytest.mark.asyncio
async def test_benchmark_market_series_supports_paging_tokens() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    composition_weight=Decimal("0.3"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX3",
                    composition_weight=Decimal("0.2"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(
            side_effect=[["IDX1", "IDX2", "IDX3"], ["IDX3"]]
        ),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    first_page = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=None),
        ),
    )
    assert [row.index_id for row in first_page.component_series] == ["IDX1", "IDX2"]
    assert first_page.page.returned_component_count == 2
    assert first_page.page.next_page_token is not None

    second_page = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=first_page.page.next_page_token),
        ),
    )
    assert [row.index_id for row in second_page.component_series] == ["IDX3"]
    assert second_page.page.returned_component_count == 1
    assert second_page.page.next_page_token is None


@pytest.mark.asyncio
async def test_benchmark_market_series_reads_page_scoped_component_evidence() -> None:
    service = make_service()
    component_rows = [
        SimpleNamespace(
            index_id="IDX1",
            composition_weight=Decimal("0.5"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=None,
            quality_status="accepted",
        ),
        SimpleNamespace(
            index_id="IDX2",
            composition_weight=Decimal("0.3"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=None,
            quality_status="accepted",
        ),
    ]
    second_page_component_rows = [
        SimpleNamespace(
            index_id="IDX3",
            composition_weight=Decimal("0.2"),
            composition_effective_from=date(2026, 1, 1),
            composition_effective_to=None,
            quality_status="accepted",
        )
    ]
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(
            side_effect=[["IDX1", "IDX2", "IDX3"], ["IDX3"]]
        ),
        list_benchmark_components_overlapping_window=AsyncMock(
            side_effect=[component_rows, second_page_component_rows]
        ),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=None),
        ),
    )

    assert [row.index_id for row in response.component_series] == ["IDX1", "IDX2"]
    assert response.page.next_page_token is not None

    second_page = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=2, page_token=response.page.next_page_token),
        ),
    )

    assert [row.index_id for row in second_page.component_series] == ["IDX3"]
    assert second_page.page.next_page_token is None
    service._reference_repository.list_benchmark_component_index_ids_overlapping_window.assert_any_await(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        after_index_id=None,
        limit=3,
    )
    service._reference_repository.list_benchmark_component_index_ids_overlapping_window.assert_any_await(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        after_index_id="IDX2",
        limit=3,
    )
    service._reference_repository.list_benchmark_components_overlapping_window.assert_any_await(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        index_ids=["IDX1", "IDX2"],
    )
    service._reference_repository.list_benchmark_components_overlapping_window.assert_any_await(
        benchmark_id="B1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        index_ids=["IDX3"],
    )
    service._reference_repository.list_index_price_points.assert_any_await(
        index_ids=["IDX1", "IDX2"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    service._reference_repository.list_index_price_points.assert_any_await(
        index_ids=["IDX3"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )


@pytest.mark.asyncio
async def test_benchmark_market_series_reads_evidence_inputs_sequentially() -> None:
    service = make_service()
    call_order: list[str] = []

    def _sequential_side_effect(name: str, result: object) -> Callable[..., Awaitable[object]]:
        async def _read(**kwargs: object) -> object:
            call_order.append(name)
            return result

        return _read

    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="EUR")),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(return_value=["IDX1"]),
        list_benchmark_components_overlapping_window=AsyncMock(
            side_effect=_sequential_side_effect(
                "components",
                [
                    SimpleNamespace(
                        index_id="IDX1",
                        composition_weight=Decimal("0.5"),
                        composition_effective_from=date(2026, 1, 1),
                        composition_effective_to=None,
                        quality_status="accepted",
                    )
                ],
            )
        ),
        list_index_price_points=AsyncMock(
            side_effect=_sequential_side_effect(
                "index_prices",
                [
                    SimpleNamespace(
                        index_id="IDX1",
                        series_date=date(2026, 1, 1),
                        index_price=Decimal("100"),
                        series_currency="EUR",
                        quality_status="accepted",
                    )
                ],
            )
        ),
        list_index_return_points=AsyncMock(
            side_effect=_sequential_side_effect(
                "index_returns",
                [
                    SimpleNamespace(
                        index_id="IDX1",
                        series_date=date(2026, 1, 1),
                        index_return=Decimal("0.01"),
                        series_currency="EUR",
                        quality_status="accepted",
                    )
                ],
            )
        ),
        list_benchmark_return_points=AsyncMock(
            side_effect=_sequential_side_effect(
                "benchmark_returns",
                [
                    SimpleNamespace(
                        series_date=date(2026, 1, 1),
                        benchmark_return=Decimal("0.008"),
                        return_period="1d",
                        return_convention="total_return_index",
                        series_currency="EUR",
                        quality_status="accepted",
                    )
                ],
            )
        ),
        get_fx_rates=AsyncMock(
            side_effect=_sequential_side_effect(
                "fx_rates",
                {date(2026, 1, 1): Decimal("1.1")},
            )
        ),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "index_return", "benchmark_return", "fx_rate"],
            page=SimpleNamespace(page_size=1, page_token=None),
        ),
    )

    assert response.component_series[0].points[0].fx_rate == Decimal("1.1")
    assert (
        response.normalization_status
        == "native_component_series_with_benchmark_to_target_fx_context"
    )
    assert call_order == [
        "components",
        "index_prices",
        "index_returns",
        "benchmark_returns",
        "fx_rates",
    ]


@pytest.mark.asyncio
async def test_benchmark_market_series_quality_summary_is_page_scoped() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    composition_weight=Decimal("0.5"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(
            return_value=["IDX1", "IDX2"]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status=" Accepted ",
                ),
                SimpleNamespace(
                    index_id="IDX2",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("200"),
                    series_currency="USD",
                    quality_status="estimated",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price"],
            page=SimpleNamespace(page_size=1, page_token=None),
        ),
    )

    assert [row.index_id for row in response.component_series] == ["IDX1"]
    assert response.quality_status_summary == {"accepted": 1}


@pytest.mark.asyncio
async def test_benchmark_market_series_rejects_page_token_scope_mismatch() -> None:
    service = make_service()
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"scope_fingerprint": "other-scope", "last_index_id": "IDX1"}
    )
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
    )

    with pytest.raises(ValueError, match="page token does not match request scope"):
        await service.get_benchmark_market_series(
            benchmark_id="B1",
            request=SimpleNamespace(
                as_of_date=date(2026, 1, 1),
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
                frequency="daily",
                target_currency=None,
                series_fields=["index_price"],
                page=SimpleNamespace(page_size=2, page_token=token),
            ),
        )


@pytest.mark.asyncio
async def test_benchmark_market_series_honors_window_rebalances() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.60"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 1, 1),
                ),
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.55"),
                    composition_effective_from=date(2026, 1, 2),
                    composition_effective_to=None,
                ),
                SimpleNamespace(
                    index_id="IDX_B",
                    composition_weight=Decimal("0.40"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=date(2026, 1, 1),
                ),
                SimpleNamespace(
                    index_id="IDX_C",
                    composition_weight=Decimal("0.45"),
                    composition_effective_from=date(2026, 1, 2),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(
            return_value=["IDX_A", "IDX_B", "IDX_C"]
        ),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("101"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_B",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("200"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    index_id="IDX_C",
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("300"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
                SimpleNamespace(
                    series_date=date(2026, 1, 2),
                    benchmark_return=Decimal("0.02"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        get_fx_rates=AsyncMock(return_value={}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 2),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
            target_currency=None,
            series_fields=["index_price", "component_weight", "benchmark_return"],
            page=SimpleNamespace(page_size=10, page_token=None),
        ),
    )

    assert [row.index_id for row in response.component_series] == ["IDX_A", "IDX_B", "IDX_C"]
    idx_a_points = next(row.points for row in response.component_series if row.index_id == "IDX_A")
    idx_b_points = next(row.points for row in response.component_series if row.index_id == "IDX_B")
    idx_c_points = next(row.points for row in response.component_series if row.index_id == "IDX_C")
    assert [point.component_weight for point in idx_a_points] == [
        Decimal("0.60"),
        Decimal("0.55"),
    ]
    assert [point.component_weight for point in idx_b_points] == [Decimal("0.40"), None]
    assert [point.component_weight for point in idx_c_points] == [None, Decimal("0.45")]


@pytest.mark.asyncio
async def test_benchmark_market_series_honors_requested_series_fields() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.60"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(return_value=["IDX_A"]),
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_index_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        list_benchmark_return_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    benchmark_return=Decimal("0.02"),
                    series_currency="USD",
                    quality_status="accepted",
                ),
            ]
        ),
        get_fx_rates=AsyncMock(return_value={date(2026, 1, 1): Decimal("1.10")}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
            target_currency="EUR",
            series_fields=["benchmark_return", "component_weight"],
            page=SimpleNamespace(page_size=10, page_token=None),
        ),
    )

    point = response.component_series[0].points[0]
    assert point.index_price is None
    assert point.index_return is None
    assert point.benchmark_return == Decimal("0.02")
    assert point.component_weight == Decimal("0.60")
    assert point.fx_rate is None
    service._reference_repository.list_index_price_points.assert_not_awaited()
    service._reference_repository.list_index_return_points.assert_not_awaited()
    service._reference_repository.list_benchmark_return_points.assert_awaited_once()
    service._reference_repository.get_fx_rates.assert_not_awaited()


@pytest.mark.asyncio
async def test_benchmark_market_series_uses_fx_dates_when_only_fx_rate_requested() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        get_benchmark_definition=AsyncMock(return_value=SimpleNamespace(benchmark_currency="USD")),
        list_benchmark_components_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX_A",
                    composition_weight=Decimal("0.60"),
                    composition_effective_from=date(2026, 1, 1),
                    composition_effective_to=None,
                ),
            ]
        ),
        list_benchmark_component_index_ids_overlapping_window=AsyncMock(return_value=["IDX_A"]),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={date(2026, 1, 1): Decimal("1.10")}),
    )

    response = await service.get_benchmark_market_series(
        benchmark_id="B1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)),
            frequency="daily",
            target_currency="EUR",
            series_fields=["fx_rate"],
            page=SimpleNamespace(page_size=10, page_token=None),
        ),
    )

    point = response.component_series[0].points[0]
    assert point.series_date == date(2026, 1, 1)
    assert point.fx_rate == Decimal("1.10")
    assert point.index_price is None
    assert point.index_return is None
    assert point.benchmark_return is None
    assert point.component_weight is None
    service._reference_repository.list_index_price_points.assert_not_awaited()
    service._reference_repository.list_index_return_points.assert_not_awaited()
    service._reference_repository.list_benchmark_return_points.assert_not_awaited()
