from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.allocation_calculator import (
    AllocationInputRow,
    calculate_allocation_views,
)


def _instrument(
    security_id: str,
    *,
    currency: str = "USD",
    asset_class: str | None = "EQUITY",
    sector: str | None = "TECH",
    country_of_risk: str | None = "US",
    product_type: str | None = "EQUITY",
    rating: str | None = "A",
    issuer_id: str | None = "ISSUER_A",
    issuer_name: str | None = "Issuer A",
    ultimate_parent_issuer_id: str | None = "PARENT_A",
    ultimate_parent_issuer_name: str | None = "Parent A",
):
    return SimpleNamespace(
        security_id=security_id,
        currency=currency,
        asset_class=asset_class,
        sector=sector,
        country_of_risk=country_of_risk,
        product_type=product_type,
        rating=rating,
        issuer_id=issuer_id,
        issuer_name=issuer_name,
        ultimate_parent_issuer_id=ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=ultimate_parent_issuer_name,
    )


def _snapshot(security_id: str):
    return SimpleNamespace(security_id=security_id)


def _bucket_values(result, dimension: str) -> dict[str, Decimal]:
    view = next(view for view in result.views if view.dimension == dimension)
    return {
        bucket.dimension_value: bucket.market_value_reporting_currency
        for bucket in view.buckets
    }


def test_calculate_allocation_views_supports_all_reporting_dimensions() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", country_of_risk="US"),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("100"),
            )
        ],
        dimensions=[
            "asset_class",
            "currency",
            "sector",
            "country",
            "region",
            "product_type",
            "rating",
            "issuer_id",
            "issuer_name",
            "ultimate_parent_issuer_id",
            "ultimate_parent_issuer_name",
        ],
    )

    assert result.total_market_value_reporting_currency == Decimal("100")
    assert _bucket_values(result, "asset_class") == {"EQUITY": Decimal("100")}
    assert _bucket_values(result, "currency") == {"USD": Decimal("100")}
    assert _bucket_values(result, "sector") == {"TECH": Decimal("100")}
    assert _bucket_values(result, "country") == {"US": Decimal("100")}
    assert _bucket_values(result, "region") == {"North America": Decimal("100")}
    assert _bucket_values(result, "product_type") == {"EQUITY": Decimal("100")}
    assert _bucket_values(result, "rating") == {"A": Decimal("100")}
    assert _bucket_values(result, "issuer_id") == {"ISSUER_A": Decimal("100")}
    assert _bucket_values(result, "issuer_name") == {"Issuer A": Decimal("100")}
    assert _bucket_values(result, "ultimate_parent_issuer_id") == {"PARENT_A": Decimal("100")}
    assert _bucket_values(result, "ultimate_parent_issuer_name") == {
        "Parent A": Decimal("100")
    }


def test_calculate_allocation_views_groups_weights_and_position_counts() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", asset_class="EQUITY"),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("100"),
            ),
            AllocationInputRow(
                instrument=_instrument("SEC2", asset_class="EQUITY"),
                snapshot=_snapshot("SEC2"),
                market_value_reporting_currency=Decimal("50"),
            ),
            AllocationInputRow(
                instrument=_instrument("SEC3", asset_class="BOND"),
                snapshot=_snapshot("SEC3"),
                market_value_reporting_currency=Decimal("50"),
            ),
        ],
        dimensions=["asset_class"],
    )

    view = result.views[0]
    buckets = {bucket.dimension_value: bucket for bucket in view.buckets}

    assert result.total_market_value_reporting_currency == Decimal("200")
    assert buckets["EQUITY"].market_value_reporting_currency == Decimal("150")
    assert buckets["EQUITY"].weight == Decimal("0.75")
    assert buckets["EQUITY"].position_count == 2
    assert buckets["BOND"].market_value_reporting_currency == Decimal("50")
    assert buckets["BOND"].weight == Decimal("0.25")
    assert buckets["BOND"].position_count == 1


def test_calculate_allocation_views_uses_unclassified_for_missing_dimension_values() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", sector=None),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("100"),
            )
        ],
        dimensions=["sector"],
    )

    assert _bucket_values(result, "sector") == {"UNCLASSIFIED": Decimal("100")}


def test_calculate_allocation_views_uses_snapshot_id_as_cash_currency_fallback() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=None,
                snapshot=_snapshot("CASH_USD"),
                market_value_reporting_currency=Decimal("25"),
            )
        ],
        dimensions=["currency"],
    )

    assert _bucket_values(result, "currency") == {"CASH_USD": Decimal("25")}


def test_calculate_allocation_views_keeps_zero_total_weights_at_zero() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", asset_class="EQUITY"),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("0"),
            )
        ],
        dimensions=["asset_class"],
    )

    bucket = result.views[0].buckets[0]
    assert result.total_market_value_reporting_currency == Decimal("0")
    assert bucket.weight == Decimal("0")
