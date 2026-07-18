from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from types import SimpleNamespace

from portfolio_common.portfolio_allocation import (
    AllocationContributorInput,
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
        bucket.dimension_value: bucket.market_value_reporting_currency for bucket in view.buckets
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
    assert _bucket_values(result, "ultimate_parent_issuer_name") == {"Parent A": Decimal("100")}


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


def test_calculate_allocation_views_canonicalizes_bucket_keys_by_dimension() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument(
                    "SEC1",
                    asset_class=" equity ",
                    currency=" usd ",
                    sector=" tech ",
                    country_of_risk=" us ",
                    product_type="Equity",
                    rating=" a ",
                    issuer_id=" issuer_a ",
                    issuer_name=" Issuer A ",
                ),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("100"),
            ),
            AllocationInputRow(
                instrument=_instrument(
                    "SEC2",
                    asset_class="EQUITY",
                    currency="USD",
                    sector="TECH",
                    country_of_risk="US",
                    product_type="Equity",
                    rating="A",
                    issuer_id="ISSUER_A",
                    issuer_name="Issuer A",
                ),
                snapshot=_snapshot("SEC2"),
                market_value_reporting_currency=Decimal("50"),
            ),
        ],
        dimensions=[
            "asset_class",
            "currency",
            "sector",
            "country",
            "region",
            "rating",
            "issuer_id",
            "issuer_name",
        ],
    )

    assert _bucket_values(result, "asset_class") == {"EQUITY": Decimal("150")}
    assert _bucket_values(result, "currency") == {"USD": Decimal("150")}
    assert _bucket_values(result, "sector") == {"TECH": Decimal("150")}
    assert _bucket_values(result, "country") == {"US": Decimal("150")}
    assert _bucket_values(result, "region") == {"North America": Decimal("150")}
    assert _bucket_values(result, "rating") == {"A": Decimal("150")}
    assert _bucket_values(result, "issuer_id") == {"ISSUER_A": Decimal("150")}
    assert _bucket_values(result, "issuer_name") == {"Issuer A": Decimal("150")}


def test_calculate_allocation_views_uses_unclassified_for_missing_dimension_values() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", sector=None),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("100"),
                contributor=_direct_contributor("SEC1", 1),
            )
        ],
        dimensions=["sector"],
        contributor_limit_per_bucket=50,
    )

    assert _bucket_values(result, "sector") == {"UNCLASSIFIED": Decimal("100")}
    assert result.views[0].buckets[0].contributors[0].contributor.security_id == "SEC1"


def test_calculate_allocation_views_uses_snapshot_id_as_cash_currency_fallback() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=None,
                snapshot=_snapshot("CASH_USD"),
                market_value_reporting_currency=Decimal("25"),
                contributor=_direct_contributor("CASH_USD", 1),
            )
        ],
        dimensions=["currency"],
        contributor_limit_per_bucket=50,
    )

    assert _bucket_values(result, "currency") == {"CASH_USD": Decimal("25")}
    contributor = result.views[0].buckets[0].contributors[0].contributor
    assert contributor.contributor_type == "direct_position"
    assert contributor.security_id == "CASH_USD"


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


def _direct_contributor(security_id: str, snapshot_id: int) -> AllocationContributorInput:
    return AllocationContributorInput(
        contributor_type="direct_position",
        portfolio_id="PORT_1",
        security_id=security_id,
        booked_security_id=security_id,
        source_snapshot_id=snapshot_id,
    )


def test_calculate_allocation_views_bounds_and_reconciles_contributors() -> None:
    rows = [
        AllocationInputRow(
            instrument=_instrument("SEC1", asset_class="EQUITY"),
            snapshot=_snapshot("SEC1"),
            market_value_reporting_currency=Decimal("100"),
            contributor=_direct_contributor("SEC1", 1),
        ),
        AllocationInputRow(
            instrument=_instrument("SEC2", asset_class="EQUITY"),
            snapshot=_snapshot("SEC2"),
            market_value_reporting_currency=Decimal("-90"),
            contributor=_direct_contributor("SEC2", 2),
        ),
        AllocationInputRow(
            instrument=_instrument("SEC3", asset_class="EQUITY"),
            snapshot=_snapshot("SEC3"),
            market_value_reporting_currency=Decimal("50"),
            contributor=_direct_contributor("SEC3", 3),
        ),
    ]

    result = calculate_allocation_views(
        rows=rows,
        dimensions=["asset_class"],
        contributor_limit_per_bucket=2,
    )
    bucket = result.views[0].buckets[0]

    assert bucket.market_value_reporting_currency == Decimal("60")
    assert bucket.position_count == 3
    assert bucket.contributor_count == 3
    assert bucket.contributors_truncated is True
    assert [contributor.contributor.security_id for contributor in bucket.contributors] == [
        "SEC1",
        "SEC2",
    ]
    assert (
        sum(
            (item.market_value_reporting_currency for item in bucket.contributors),
            Decimal("0"),
        )
        + bucket.omitted_market_value_reporting_currency
        == bucket.market_value_reporting_currency
    )
    assert bucket.omitted_market_value_reporting_currency == Decimal("50")


def test_allocation_lineage_is_order_independent_and_binds_source_identity() -> None:
    contributor = AllocationContributorInput(
        contributor_type="look_through_component",
        portfolio_id="PORT_1",
        security_id="ETF_1",
        booked_security_id="FUND_1",
        source_snapshot_id=11,
        component_record_id=21,
        component_weight=Decimal("0.6"),
        component_effective_from=date(2026, 1, 1),
        component_source_system="fund-master",
        component_source_record_id="COMP_21",
    )
    component_row = AllocationInputRow(
        instrument=_instrument("ETF_1", asset_class="EQUITY"),
        snapshot=_snapshot("ETF_1"),
        market_value_reporting_currency=Decimal("60"),
        contributor=contributor,
    )
    direct_row = AllocationInputRow(
        instrument=_instrument("SEC_2", asset_class="BOND"),
        snapshot=_snapshot("SEC_2"),
        market_value_reporting_currency=Decimal("40"),
        contributor=_direct_contributor("SEC_2", 12),
    )

    first = calculate_allocation_views(
        rows=[component_row, direct_row],
        dimensions=["asset_class"],
        contributor_limit_per_bucket=50,
    )
    reordered = calculate_allocation_views(
        rows=[direct_row, component_row],
        dimensions=["asset_class"],
        contributor_limit_per_bucket=50,
    )
    corrected = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=component_row.instrument,
                snapshot=component_row.snapshot,
                market_value_reporting_currency=component_row.market_value_reporting_currency,
                contributor=replace(
                    contributor,
                    component_source_record_id="COMP_21_REV_2",
                ),
            ),
            direct_row,
        ],
        dimensions=["asset_class"],
        contributor_limit_per_bucket=50,
    )

    assert first.calculation_lineage == reordered.calculation_lineage
    assert (
        corrected.calculation_lineage.input_content_hash
        != first.calculation_lineage.input_content_hash
    )
    assert corrected.calculation_lineage.algorithm_id == "PORTFOLIO_ALLOCATION"
    assert corrected.calculation_lineage.intermediate_precision == 28


def test_allocation_weight_is_independent_of_ambient_decimal_precision() -> None:
    rows = [
        AllocationInputRow(
            instrument=_instrument("SEC1", asset_class="EQUITY"),
            snapshot=_snapshot("SEC1"),
            market_value_reporting_currency=Decimal("1"),
        ),
        AllocationInputRow(
            instrument=_instrument("SEC2", asset_class="BOND"),
            snapshot=_snapshot("SEC2"),
            market_value_reporting_currency=Decimal("2"),
        ),
    ]

    with localcontext() as context:
        context.prec = 6
        result = calculate_allocation_views(rows=rows, dimensions=["asset_class"])

    assert result.views[0].buckets[0].weight == Decimal("0.6666666666666666666666666667")


def test_empty_allocation_has_deterministic_lineage_and_no_buckets() -> None:
    result = calculate_allocation_views(
        rows=[],
        dimensions=["asset_class", "currency"],
        contributor_limit_per_bucket=50,
    )

    assert result.total_market_value_reporting_currency == Decimal("0")
    assert [view.buckets for view in result.views] == [(), ()]
    assert result.calculation_lineage.algorithm_id == "PORTFOLIO_ALLOCATION"


def test_zero_value_bucket_exposes_unavailable_contributor_weight() -> None:
    result = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=_instrument("SEC1", asset_class="EQUITY"),
                snapshot=_snapshot("SEC1"),
                market_value_reporting_currency=Decimal("10"),
                contributor=_direct_contributor("SEC1", 1),
            ),
            AllocationInputRow(
                instrument=_instrument("SEC2", asset_class="EQUITY"),
                snapshot=_snapshot("SEC2"),
                market_value_reporting_currency=Decimal("-10"),
                contributor=_direct_contributor("SEC2", 2),
            ),
        ],
        dimensions=["asset_class"],
        contributor_limit_per_bucket=50,
    )

    assert [item.bucket_weight for item in result.views[0].buckets[0].contributors] == [None, None]


def test_large_allocation_retains_only_bounded_top_contributors() -> None:
    rows = [
        AllocationInputRow(
            instrument=_instrument(f"SEC_{index}", asset_class="EQUITY"),
            snapshot=_snapshot(f"SEC_{index}"),
            market_value_reporting_currency=Decimal(index),
            contributor=_direct_contributor(f"SEC_{index}", index + 1),
        )
        for index in range(10_000)
    ]

    result = calculate_allocation_views(
        rows=rows,
        dimensions=["asset_class", "currency", "sector", "region"],
        contributor_limit_per_bucket=50,
        calculation_context={"portfolio_id": "PORT_1", "reporting_currency": "USD"},
    )
    bucket = result.views[0].buckets[0]

    assert bucket.position_count == 10_000
    assert bucket.contributor_count == 10_000
    assert len(bucket.contributors) == 50
    assert bucket.contributors_truncated is True
    assert bucket.contributors[0].contributor.security_id == "SEC_9999"
    assert (
        sum(
            (item.market_value_reporting_currency for item in bucket.contributors),
            bucket.omitted_market_value_reporting_currency,
        )
        == bucket.market_value_reporting_currency
    )
