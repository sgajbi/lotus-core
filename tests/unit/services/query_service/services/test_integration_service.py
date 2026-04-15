from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.reconciliation_quality import BLOCKED, COMPLETE, PARTIAL, STALE, UNRECONCILED
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.integration_service import IntegrationService


def make_service() -> IntegrationService:
    return IntegrationService(AsyncMock(spec=AsyncSession))


def test_to_coverage_response_uses_exact_observed_dates_when_present() -> None:
    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
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
    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
        coverage=coverage,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        request_fingerprint="fp-coverage-test",
    )

    assert response.data_quality_status == expected_status


def test_to_coverage_response_carries_latest_evidence_timestamp() -> None:
    latest_evidence_timestamp = datetime(2026, 1, 3, 14, 30, tzinfo=UTC)

    response = IntegrationService._to_coverage_response(  # pylint: disable=protected-access
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
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            rows,
            required_count=len(rows),
        )
        == PARTIAL
    )
    assert (
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            [SimpleNamespace(quality_status="blocked")],
            required_count=1,
        )
        == BLOCKED
    )
    assert (
        IntegrationService._market_reference_data_quality_status(  # pylint: disable=protected-access
            [SimpleNamespace()],
            required_count=1,
        )
        == "UNKNOWN"
    )


def test_latest_reference_evidence_timestamp_uses_durable_reference_timestamps() -> None:
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)

    assert (
        IntegrationService._latest_reference_evidence_timestamp(  # pylint: disable=protected-access
            [
                SimpleNamespace(source_timestamp=older_source_timestamp),
                SimpleNamespace(updated_at=latest_updated_at),
            ]
        )
        == latest_updated_at
    )


def test_canonical_consumer_system_mappings() -> None:
    service = make_service()
    assert service._canonical_consumer_system("lotus-manage") == "lotus-manage"
    assert service._canonical_consumer_system("lotus-gateway") == "lotus-gateway"
    assert service._canonical_consumer_system("UI") == "UI"
    assert service._canonical_consumer_system("Custom-System") == "custom-system"
    assert service._canonical_consumer_system(None) == "unknown"
    assert service._canonical_consumer_system("   ") == "unknown"


def test_load_policy_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()

    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    assert service._load_policy() == {}

    monkeypatch.setenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", "not-json")
    assert service._load_policy() == {}

    monkeypatch.setenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", '["bad"]')
    assert service._load_policy() == {}

    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strict_mode": true, "consumers": {"lotus-manage": ["OVERVIEW"]}}',
    )
    loaded = service._load_policy()
    assert loaded["strict_mode"] is True
    assert "consumers" in loaded


def test_normalize_and_resolve_consumer_sections() -> None:
    service = make_service()
    assert service._normalize_sections(None) is None
    assert service._normalize_sections([" overview ", "HOLDINGS", "", 123]) == [
        "OVERVIEW",
        "HOLDINGS",
    ]

    sections, key = service._resolve_consumer_sections(None, "lotus-manage")
    assert sections is None
    assert key is None

    sections, key = service._resolve_consumer_sections(
        {"lotus-manage": ["overview"], "other": ["x"]},
        "lotus-manage",
    )
    assert sections == ["OVERVIEW"]
    assert key == "lotus-manage"

    sections, key = service._resolve_consumer_sections({"foo": ["x"]}, "lotus-manage")
    assert sections is None
    assert key is None


def test_resolve_policy_context_default(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    monkeypatch.delenv("LOTUS_CORE_POLICY_VERSION", raising=False)

    ctx = service._resolve_policy_context(tenant_id="default", consumer_system="lotus-manage")
    assert ctx.policy_version == "tenant-default-v1"
    assert ctx.policy_source == "default"
    assert ctx.matched_rule_id == "default"
    assert ctx.strict_mode is False
    assert ctx.allowed_sections is None
    assert "NO_ALLOWED_SECTION_RESTRICTION" in ctx.warnings


def test_resolve_policy_context_global_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"strict_mode":false,'
            '"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]},'
            '"tenants":{"tenant-a":{"strict_mode":true,"consumers":{"lotus-manage":["ALLOCATION"]}}}}'
        ),
    )
    monkeypatch.setenv("LOTUS_CORE_POLICY_VERSION", "tenant-v7")

    global_ctx = service._resolve_policy_context(
        tenant_id="default",
        consumer_system="lotus-manage",
    )
    assert global_ctx.policy_source == "global"
    assert global_ctx.matched_rule_id == "global.consumers.lotus-manage"
    assert global_ctx.strict_mode is False
    assert global_ctx.allowed_sections == ["OVERVIEW", "HOLDINGS"]

    tenant_ctx = service._resolve_policy_context(
        tenant_id="tenant-a",
        consumer_system="lotus-manage",
    )
    assert tenant_ctx.policy_version == "tenant-v7"
    assert tenant_ctx.policy_source == "tenant"
    assert tenant_ctx.matched_rule_id == "tenant.tenant-a.consumers.lotus-manage"
    assert tenant_ctx.strict_mode is True
    assert tenant_ctx.allowed_sections == ["ALLOCATION"]


def test_resolve_policy_context_tenant_default_sections_and_strict_mode_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"tenants":{"tenant-x":{"strict_mode":true,"default_sections":["OVERVIEW"]},'
            '"tenant-y":{"strict_mode":true}}}'
        ),
    )

    tenant_default_ctx = service._resolve_policy_context(
        tenant_id="tenant-x",
        consumer_system="lotus-manage",
    )
    assert tenant_default_ctx.policy_source == "tenant"
    assert tenant_default_ctx.matched_rule_id == "tenant.tenant-x.default_sections"
    assert tenant_default_ctx.allowed_sections == ["OVERVIEW"]
    assert tenant_default_ctx.strict_mode is True

    strict_only_ctx = service._resolve_policy_context(
        tenant_id="tenant-y",
        consumer_system="lotus-manage",
    )
    assert strict_only_ctx.policy_source == "tenant"
    assert strict_only_ctx.matched_rule_id == "tenant.tenant-y.strict_mode"
    assert strict_only_ctx.allowed_sections is None
    assert strict_only_ctx.strict_mode is True


def test_get_effective_policy_filters_requested_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]}}',
    )

    response = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=["overview", "allocation", "holdings"],
    )
    assert response.consumer_system == "lotus-manage"
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.policy_provenance.matched_rule_id == "global.consumers.lotus-manage"


def test_get_effective_policy_no_allowed_restriction_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)

    response = service.get_effective_policy(
        consumer_system="custom-client",
        tenant_id="default",
        include_sections=["overview", "allocation"],
    )
    assert response.consumer_system == "custom-client"
    assert response.allowed_sections == ["OVERVIEW", "ALLOCATION"]
    assert "NO_ALLOWED_SECTION_RESTRICTION" in response.warnings


def test_get_effective_policy_uses_configured_allowed_sections_when_unrequested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-manage":["HOLDINGS","ALLOCATION"]}}',
    )

    response = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=None,
    )

    assert response.consumer_system == "lotus-manage"
    assert response.allowed_sections == ["HOLDINGS", "ALLOCATION"]


@pytest.mark.asyncio
async def test_reference_contract_methods() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        resolve_benchmark_assignment=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                benchmark_id="B1",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                assignment_source="policy",
                assignment_status="active",
                policy_pack_id="pack",
                source_system="lotus-manage",
                assignment_recorded_at=date(2026, 1, 1),
                assignment_version=1,
            )
        ),
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
        list_index_definitions=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    index_name="Index 1",
                    index_currency="USD",
                    index_type="equity",
                    index_status="active",
                    index_provider="provider",
                    index_market="global",
                    classification_set_id="set1",
                    classification_labels={"sector": "technology"},
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                    source_timestamp=None,
                    source_vendor="vendor",
                    source_record_id="idx-src",
                )
            ]
        ),
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
        list_index_price_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="accepted",
                )
            ]
        ),
        list_index_return_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 1),
                    index_return=Decimal("0.01"),
                    return_period="1d",
                    return_convention="total_return_index",
                    series_currency="USD",
                    quality_status="accepted",
                )
            ]
        ),
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

    assignment = await service.resolve_benchmark_assignment("P1", date(2026, 1, 1))
    assert assignment is not None
    assert assignment.benchmark_id == "B1"
    assert assignment.product_name == "BenchmarkAssignment"
    assert assignment.generated_at.tzinfo is not None
    assert assignment.restatement_version == "current"
    assert assignment.reconciliation_status == "UNKNOWN"
    assert assignment.data_quality_status == "UNKNOWN"

    definition = await service.get_benchmark_definition("B1", date(2026, 1, 1))
    assert definition is not None
    assert definition.benchmark_id == "B1"

    composition_window = await service.get_benchmark_composition_window(
        "B1",
        SimpleNamespace(
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
        ),
    )
    assert composition_window is not None
    assert composition_window.benchmark_currency == "USD"
    assert composition_window.segments[0].index_id == "IDX1"
    assert composition_window.product_name == "BenchmarkConstituentWindow"
    assert composition_window.as_of_date == date(2026, 3, 31)

    benchmark_catalog = await service.list_benchmark_catalog(date(2026, 1, 1), None, None, None)
    assert benchmark_catalog.records == []

    index_catalog = await service.list_index_catalog(date(2026, 1, 1), None, None, None)
    assert index_catalog.records[0].index_id == "IDX1"

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

    index_price = await service.get_index_price_series(
        index_id="IDX1",
        request=SimpleNamespace(
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert index_price.points
    assert index_price.product_name == "IndexSeriesWindow"
    assert index_price.as_of_date == date(2026, 1, 2)

    index_return = await service.get_index_return_series(
        index_id="IDX1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 1),
            window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)),
            frequency="daily",
        ),
    )
    assert index_return.points
    assert index_return.as_of_date == date(2026, 1, 1)
    assert index_return.request_fingerprint
    assert index_return.product_name == "IndexSeriesWindow"

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
async def test_market_reference_products_expose_row_backed_quality_and_evidence_timestamp() -> None:
    service = make_service()
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_source_timestamp = datetime(2026, 1, 3, 11, 15, tzinfo=UTC)
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_index_price_series=AsyncMock(
            return_value=[
                SimpleNamespace(
                    series_date=date(2026, 1, 2),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="accepted",
                    source_timestamp=older_source_timestamp,
                ),
                SimpleNamespace(
                    series_date=date(2026, 1, 3),
                    index_price=Decimal("101"),
                    series_currency="USD",
                    value_convention="close_price",
                    quality_status="estimated",
                    source_timestamp=latest_source_timestamp,
                ),
            ]
        )
    )

    response = await service.get_index_price_series(
        index_id="IDX1",
        request=SimpleNamespace(
            as_of_date=date(2026, 1, 3),
            window=SimpleNamespace(start_date=date(2026, 1, 2), end_date=date(2026, 1, 3)),
            frequency="daily",
        ),
    )

    assert response.product_name == "IndexSeriesWindow"
    assert response.data_quality_status == PARTIAL
    assert response.latest_evidence_timestamp == latest_source_timestamp
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is None


@pytest.mark.asyncio
async def test_reference_contract_none_and_fx_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        resolve_benchmark_assignment=AsyncMock(return_value=None),
        get_benchmark_definition=AsyncMock(
            side_effect=[
                None,
                SimpleNamespace(benchmark_currency="EUR"),
                SimpleNamespace(benchmark_currency="EUR"),
            ]
        ),
        list_benchmark_definitions_overlapping_window=AsyncMock(return_value=[]),
        list_benchmark_components=AsyncMock(return_value=[]),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
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
        list_index_definitions=AsyncMock(return_value=[]),
        list_index_price_points=AsyncMock(return_value=[]),
        list_index_return_points=AsyncMock(return_value=[]),
        list_benchmark_return_points=AsyncMock(return_value=[]),
        get_fx_rates=AsyncMock(return_value={}),
        list_index_price_series=AsyncMock(return_value=[]),
        list_index_return_series=AsyncMock(return_value=[]),
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

    assert await service.resolve_benchmark_assignment("P1", date(2026, 1, 1)) is None
    assert await service.get_benchmark_definition("B1", date(2026, 1, 1)) is None
    assert (
        await service.get_benchmark_composition_window(
            "B1",
            SimpleNamespace(
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
            ),
        )
        is None
    )

    benchmark_catalog = await service.list_benchmark_catalog(
        date(2026, 1, 1), "single_index", "EUR", "active"
    )
    assert benchmark_catalog.records

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

    monkeypatch.setenv(
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"tenants":{"tenant-z":{"strict_mode":false,"default_sections":["OVERVIEW"]}}}',
    )
    ctx = service._resolve_policy_context("tenant-z", "lotus-manage")
    assert ctx.policy_source == "tenant"
    assert ctx.matched_rule_id == "tenant.tenant-z.default_sections"

    monkeypatch.delenv("LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    effective = service.get_effective_policy(
        consumer_system="lotus-manage",
        tenant_id="default",
        include_sections=None,
    )
    assert effective.allowed_sections == []


@pytest.mark.asyncio
async def test_benchmark_composition_window_rejects_currency_changes_within_window() -> None:
    service = make_service()
    service._reference_repository = SimpleNamespace(  # type: ignore[assignment]
        list_benchmark_definitions_overlapping_window=AsyncMock(
            return_value=[
                SimpleNamespace(benchmark_currency="USD"),
                SimpleNamespace(benchmark_currency="EUR"),
            ]
        ),
        list_benchmark_components_overlapping_window=AsyncMock(return_value=[]),
    )

    with pytest.raises(ValueError, match="currency changed within requested composition window"):
        await service.get_benchmark_composition_window(
            "B1",
            SimpleNamespace(
                window=SimpleNamespace(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
            ),
        )


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
        list_index_price_points=AsyncMock(
            return_value=[
                SimpleNamespace(
                    index_id="IDX1",
                    series_date=date(2026, 1, 1),
                    index_price=Decimal("100"),
                    series_currency="USD",
                    quality_status="accepted",
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
