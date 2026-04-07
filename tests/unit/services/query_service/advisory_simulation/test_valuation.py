from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.advisory_simulation.allocation_contract import (
    ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
)
from src.services.query_service.app.advisory_simulation.models import (
    EngineOptions,
    Money,
    ValuationMode,
)
from src.services.query_service.app.advisory_simulation.valuation import (
    ValuationService,
    build_simulated_state,
    get_fx_rate,
)
from src.services.query_service.app.services.allocation_calculator import (
    AllocationInputRow,
    calculate_allocation_views,
)
from tests.shared.factories import (
    cash,
    fx,
    market_data_snapshot,
    portfolio_snapshot,
    position,
    price,
    shelf_entry,
)


def test_get_fx_rate_supports_direct_inverse_and_same_currency() -> None:
    market_data = market_data_snapshot(fx_rates=[fx("USD/SGD", "1.35")])

    assert get_fx_rate(market_data, "USD", "SGD") == Decimal("1.35")
    assert get_fx_rate(market_data, "SGD", "USD") == Decimal("1") / Decimal("1.35")
    assert get_fx_rate(market_data, "USD", "USD") == Decimal("1.0")
    assert get_fx_rate(market_data, "EUR", "USD") is None


def test_value_position_uses_trust_snapshot_market_value_when_configured() -> None:
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")])
    portfolio = portfolio_snapshot(
        positions=[
            position("EQ_1", "2").model_copy(
                update={"market_value": Money(amount=Decimal("333"), currency="USD")}
            )
        ]
    )

    summary = ValuationService.value_position(
        portfolio.positions[0],
        market_data,
        "USD",
        EngineOptions(valuation_mode=ValuationMode.TRUST_SNAPSHOT),
        {"price_missing": [], "fx_missing": []},
    )

    assert summary.value_in_instrument_ccy.amount == Decimal("333")
    assert summary.value_in_base_ccy.amount == Decimal("333")


def test_value_position_uses_calculated_market_value_by_default() -> None:
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")])
    portfolio = portfolio_snapshot(positions=[position("EQ_1", "2")])

    summary = ValuationService.value_position(
        portfolio.positions[0],
        market_data,
        "USD",
        EngineOptions(),
        {"price_missing": [], "fx_missing": []},
    )

    assert summary.value_in_instrument_ccy.amount == Decimal("200")
    assert summary.value_in_base_ccy.amount == Decimal("200")


def test_build_simulated_state_records_missing_price_and_fx_pairs() -> None:
    portfolio = portfolio_snapshot(
        base_currency="USD",
        positions=[position("EQ_1", "2"), position("EUR_EQ", "3")],
        cash_balances=[cash("CHF", "10")],
    )
    market_data = market_data_snapshot(
        prices=[price("EUR_EQ", "10", "EUR")],
        fx_rates=[],
    )
    dq_log = {"price_missing": [], "fx_missing": [], "shelf_missing": []}

    state = build_simulated_state(
        portfolio,
        market_data,
        [shelf_entry("EQ_1", asset_class="EQUITY"), shelf_entry("EUR_EQ", asset_class="EQUITY")],
        dq_log,
        [],
        EngineOptions(),
    )

    assert state.total_value.amount == Decimal("0")
    assert dq_log["price_missing"] == ["EQ_1"]
    assert "EUR/USD" in dq_log["fx_missing"]
    assert "CHF/USD" in dq_log["fx_missing"]


def test_build_simulated_state_aggregates_asset_classes_attributes_and_cash() -> None:
    portfolio = portfolio_snapshot(
        base_currency="USD",
        positions=[position("EQ_1", "2"), position("BOND_1", "1")],
        cash_balances=[cash("USD", "50")],
    )
    market_data = market_data_snapshot(
        prices=[price("EQ_1", "100", "USD"), price("BOND_1", "200", "USD")],
        fx_rates=[],
    )
    shelf = [
        shelf_entry("EQ_1", asset_class="EQUITY").model_copy(
            update={"attributes": {"sector": "TECH"}}
        ),
        shelf_entry("BOND_1", asset_class="FIXED_INCOME").model_copy(
            update={"attributes": {"sector": "GOVT"}}
        ),
    ]

    state = build_simulated_state(
        portfolio,
        market_data,
        shelf,
        {"price_missing": [], "fx_missing": [], "shelf_missing": []},
        [],
    )

    asset_classes = {metric.key: metric.weight for metric in state.allocation_by_asset_class}
    sectors = {metric.key: metric.weight for metric in state.allocation_by_attribute["sector"]}

    assert state.total_value.amount == Decimal("450")
    assert asset_classes["EQUITY"] == Decimal("200") / Decimal("450")
    assert asset_classes["FIXED_INCOME"] == Decimal("200") / Decimal("450")
    assert asset_classes["CASH"] == Decimal("50") / Decimal("450")
    assert sectors["TECH"] == Decimal("200") / Decimal("450")
    assert sectors["GOVT"] == Decimal("200") / Decimal("450")


def test_build_simulated_state_asset_class_matches_shared_allocation_calculator() -> None:
    portfolio = portfolio_snapshot(
        base_currency="USD",
        positions=[position("EQ_1", "2"), position("BOND_1", "1")],
        cash_balances=[cash("USD", "50")],
    )
    market_data = market_data_snapshot(
        prices=[price("EQ_1", "100", "USD"), price("BOND_1", "200", "USD")],
    )
    shelf = [
        shelf_entry("EQ_1", asset_class="EQUITY"),
        shelf_entry("BOND_1", asset_class="FIXED_INCOME"),
    ]

    state = build_simulated_state(
        portfolio,
        market_data,
        shelf,
        {"price_missing": [], "fx_missing": [], "shelf_missing": []},
        [],
    )
    expected_view = calculate_allocation_views(
        rows=[
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="EQUITY"),
                snapshot=SimpleNamespace(security_id="EQ_1"),
                market_value_reporting_currency=Decimal("200"),
            ),
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="FIXED_INCOME"),
                snapshot=SimpleNamespace(security_id="BOND_1"),
                market_value_reporting_currency=Decimal("200"),
            ),
            AllocationInputRow(
                instrument=SimpleNamespace(asset_class="CASH"),
                snapshot=SimpleNamespace(security_id="CASH_USD"),
                market_value_reporting_currency=Decimal("50"),
            ),
        ],
        dimensions=["asset_class"],
    ).views[0]

    actual = {
        metric.key: (metric.value.amount, metric.weight)
        for metric in state.allocation_by_asset_class
    }
    expected = {
        bucket.dimension_value: (bucket.market_value_reporting_currency, bucket.weight)
        for bucket in expected_view.buckets
    }

    assert actual == expected


def test_build_simulated_state_emits_curated_canonical_allocation_views() -> None:
    portfolio = portfolio_snapshot(
        base_currency="USD",
        positions=[position("EQ_1", "2")],
        cash_balances=[cash("USD", "50")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")])
    shelf = [
        shelf_entry("EQ_1", asset_class="EQUITY").model_copy(
            update={
                "attributes": {
                    "sector": "TECHNOLOGY",
                    "country": "US",
                    "product_type": "EQUITY",
                    "rating": "A",
                }
            }
        )
    ]

    state = build_simulated_state(
        portfolio,
        market_data,
        shelf,
        {"price_missing": [], "fx_missing": [], "shelf_missing": []},
        [],
    )

    views_by_dimension = {view.dimension: view for view in state.allocation_views}

    assert tuple(views_by_dimension) == ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS
    assert {bucket.key for bucket in views_by_dimension["asset_class"].buckets} == {
        "CASH",
        "EQUITY",
    }
    assert {bucket.key for bucket in views_by_dimension["currency"].buckets} == {"USD"}
    assert {bucket.key for bucket in views_by_dimension["sector"].buckets} == {
        "TECHNOLOGY",
        "UNCLASSIFIED",
    }
    assert {bucket.key for bucket in views_by_dimension["country"].buckets} == {
        "US",
        "UNCLASSIFIED",
    }
    assert {bucket.key for bucket in views_by_dimension["region"].buckets} == {
        "North America",
        "UNCLASSIFIED",
    }
    assert {bucket.key for bucket in views_by_dimension["product_type"].buckets} == {
        "EQUITY",
        "UNCLASSIFIED",
    }
    assert {bucket.key for bucket in views_by_dimension["rating"].buckets} == {
        "A",
        "UNCLASSIFIED",
    }


def test_legacy_asset_class_allocation_is_derived_from_canonical_lens() -> None:
    portfolio = portfolio_snapshot(
        base_currency="USD",
        positions=[position("EQ_1", "2")],
        cash_balances=[cash("USD", "50")],
    )
    market_data = market_data_snapshot(prices=[price("EQ_1", "100", "USD")])
    shelf = [shelf_entry("EQ_1", asset_class="EQUITY")]

    state = build_simulated_state(
        portfolio,
        market_data,
        shelf,
        {"price_missing": [], "fx_missing": [], "shelf_missing": []},
        [],
    )

    canonical_asset_class = next(
        view for view in state.allocation_views if view.dimension == "asset_class"
    )
    canonical = {
        bucket.key: (bucket.value.amount, bucket.weight)
        for bucket in canonical_asset_class.buckets
    }
    legacy = {
        metric.key: (metric.value.amount, metric.weight)
        for metric in state.allocation_by_asset_class
    }

    assert legacy == canonical
