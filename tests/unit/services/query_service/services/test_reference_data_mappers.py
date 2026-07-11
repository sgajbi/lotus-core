from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.reference_data_mappers import (
    benchmark_component_series_response,
    benchmark_market_series_point,
    benchmark_return_series_point,
    classification_taxonomy_entry,
    index_price_series_point,
    index_return_series_point,
    risk_free_series_point,
)


def test_market_reference_series_points_map_provider_rows() -> None:
    series_date = date(2026, 1, 2)

    price = index_price_series_point(
        SimpleNamespace(
            series_date=series_date,
            index_price="4567.1234000000",
            series_currency="USD",
            value_convention="close_price",
            quality_status="accepted",
        )
    )
    index_return = index_return_series_point(
        SimpleNamespace(
            series_date=series_date,
            index_return="0.0023000000",
            return_period="1d",
            return_convention="total_return_index",
            series_currency="USD",
            quality_status="accepted",
        )
    )
    benchmark_return = benchmark_return_series_point(
        SimpleNamespace(
            series_date=series_date,
            benchmark_return="0.0019000000",
            return_period="1d",
            return_convention="total_return_index",
            series_currency="USD",
            quality_status="accepted",
        )
    )
    risk_free = risk_free_series_point(
        SimpleNamespace(
            series_date=series_date,
            value="0.0350000000",
            value_convention="annualized_rate",
            day_count_convention="act_360",
            compounding_convention="simple",
            series_currency="USD",
            quality_status="accepted",
        )
    )
    taxonomy = classification_taxonomy_entry(
        SimpleNamespace(
            classification_set_id="wm_global_taxonomy_v1",
            taxonomy_scope="instrument",
            dimension_name="asset_class",
            dimension_value="equity",
            dimension_description="Listed equity",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
        )
    )

    assert price.index_price == Decimal("4567.1234000000")
    assert index_return.index_return == Decimal("0.0023000000")
    assert benchmark_return.benchmark_return == Decimal("0.0019000000")
    assert risk_free.value == Decimal("0.0350000000")
    assert risk_free.day_count_convention == "act_360"
    assert taxonomy.dimension_name == "asset_class"
    assert taxonomy.dimension_value == "equity"


def test_benchmark_market_series_point_maps_selected_fields() -> None:
    series_date = date(2026, 1, 2)
    point = benchmark_market_series_point(
        series_date=series_date,
        requested_fields={
            "index_price",
            "index_return",
            "benchmark_return",
            "component_weight",
            "fx_rate",
        },
        price_row=SimpleNamespace(
            index_price="4567.1234000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        return_row=SimpleNamespace(
            index_return="0.0023000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        benchmark_return_row=SimpleNamespace(
            benchmark_return="0.0019000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        component_weight=Decimal("0.6000000000"),
        fx_rate=Decimal("1.3456000000"),
    )
    component = benchmark_component_series_response(
        index_id="IDX_MSCI_WORLD_TR",
        points=[point],
    )

    assert component.index_id == "IDX_MSCI_WORLD_TR"
    assert component.points[0].series_date == series_date
    assert component.points[0].index_price == Decimal("4567.1234000000")
    assert component.points[0].index_return == Decimal("0.0023000000")
    assert component.points[0].benchmark_return == Decimal("0.0019000000")
    assert component.points[0].component_weight == Decimal("0.6000000000")
    assert component.points[0].fx_rate == Decimal("1.3456000000")
    assert component.points[0].quality_status == "accepted"


def test_benchmark_market_series_point_omits_unrequested_fields() -> None:
    point = benchmark_market_series_point(
        series_date=date(2026, 1, 2),
        requested_fields={"index_return"},
        price_row=SimpleNamespace(
            index_price="4567.1234000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        return_row=SimpleNamespace(
            index_return="0.0023000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        benchmark_return_row=SimpleNamespace(
            benchmark_return="0.0019000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        component_weight=Decimal("0.6000000000"),
        fx_rate=Decimal("1.3456000000"),
    )

    assert point.series_currency == "USD"
    assert point.index_price is None
    assert point.index_return == Decimal("0.0023000000")
    assert point.benchmark_return is None
    assert point.component_weight is None
    assert point.fx_rate is None
    assert point.quality_status == "accepted"


def test_benchmark_market_series_point_uses_price_row_precedence_for_metadata() -> None:
    point = benchmark_market_series_point(
        series_date=date(2026, 1, 2),
        requested_fields=set(),
        price_row=SimpleNamespace(
            index_price="4567.1234000000",
            series_currency="USD",
            quality_status="accepted",
        ),
        return_row=SimpleNamespace(
            index_return="0.0023000000",
            series_currency="EUR",
            quality_status="estimated",
        ),
        benchmark_return_row=SimpleNamespace(
            benchmark_return="0.0019000000",
            series_currency="GBP",
            quality_status="blocked",
        ),
        component_weight=None,
        fx_rate=None,
    )

    assert point.series_currency == "USD"
    assert point.quality_status == "accepted"
