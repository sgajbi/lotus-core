from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.read_models import PortfolioTaxLotReadRecord
from src.services.query_service.app.services.reference_data_mappers import (
    benchmark_component_series_response,
    benchmark_definition_response,
    benchmark_market_series_point,
    benchmark_return_series_point,
    cio_model_change_affected_mandate,
    classification_taxonomy_entry,
    dpm_portfolio_universe_candidate,
    index_definition_response,
    index_price_series_point,
    index_return_series_point,
    instrument_eligibility_record,
    market_data_fx_coverage_record,
    market_data_price_coverage_record,
    missing_instrument_eligibility_record,
    missing_market_data_fx_coverage_record,
    missing_market_data_price_coverage_record,
    model_portfolio_target_row,
    portfolio_manager_book_member,
    portfolio_tax_lot_record,
    risk_free_series_point,
)


def test_benchmark_definition_response_maps_catalog_row_and_components() -> None:
    source_timestamp = datetime(2026, 1, 31, 8, tzinfo=UTC)

    response = benchmark_definition_response(
        SimpleNamespace(
            benchmark_id="BMK_GLOBAL_BALANCED_60_40",
            benchmark_name="Global Balanced 60/40",
            benchmark_type="composite",
            benchmark_currency="USD",
            return_convention="total_return_index",
            benchmark_status="active",
            benchmark_family="multi_asset",
            benchmark_provider="MSCI",
            rebalance_frequency="quarterly",
            classification_set_id="wm_global_taxonomy_v1",
            classification_labels={"asset_class": "multi_asset"},
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
            source_timestamp=source_timestamp,
            source_vendor="MSCI",
            source_record_id="bmk_60_40_v20260131",
        ),
        components=[
            SimpleNamespace(
                index_id="IDX_MSCI_WORLD_TR",
                composition_weight="0.6000000000",
                composition_effective_from=date(2026, 1, 1),
                composition_effective_to=None,
                rebalance_event_id="rebalance_2026q1",
            )
        ],
    )

    assert response.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
    assert response.classification_labels == {"asset_class": "multi_asset"}
    assert response.components[0].composition_weight == Decimal("0.6000000000")
    assert response.components[0].rebalance_event_id == "rebalance_2026q1"


def test_index_definition_response_maps_reference_catalog_row() -> None:
    source_timestamp = datetime(2026, 1, 31, 8, tzinfo=UTC)

    response = index_definition_response(
        SimpleNamespace(
            index_id="IDX_MSCI_WORLD_TR",
            index_name="MSCI World Total Return",
            index_currency="USD",
            index_type="equity_index",
            index_status="active",
            index_provider="MSCI",
            index_market="global_developed",
            classification_set_id="wm_global_taxonomy_v1",
            classification_labels={"asset_class": "equity", "region": "global"},
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
            source_timestamp=source_timestamp,
            source_vendor="MSCI",
            source_record_id="idx_world_tr_v20260131",
        )
    )

    assert response.index_id == "IDX_MSCI_WORLD_TR"
    assert response.index_provider == "MSCI"
    assert response.classification_labels == {"asset_class": "equity", "region": "global"}


def test_dpm_source_entries_map_model_and_mandate_rows() -> None:
    target = model_portfolio_target_row(
        SimpleNamespace(
            instrument_id="EQ_US_AAPL",
            target_weight="0.1200000000",
            min_weight="0.0800000000",
            max_weight=None,
            target_status="active",
            quality_status="accepted",
            source_record_id="target-1",
        )
    )
    member = portfolio_manager_book_member(
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_GLOBAL_BAL_001",
            booking_center_code="Singapore",
            portfolio_type="DISCRETIONARY",
            status="ACTIVE",
            open_date=date(2025, 3, 31),
            close_date=None,
            base_currency="USD",
        )
    )
    affected_mandate = cio_model_change_affected_mandate(
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_GLOBAL_BAL_001",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            discretionary_authority_status="active",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_PACK_BALANCED",
            risk_profile="balanced",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            binding_version="6",
            source_record_id="mandate-1",
        )
    )
    candidate = dpm_portfolio_universe_candidate(
        SimpleNamespace(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
            client_id="CIF_SG_GLOBAL_BAL_001",
            booking_center_code="Singapore",
            jurisdiction_code="SG",
            discretionary_authority_status="active",
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            policy_pack_id="POLICY_PACK_BALANCED",
            mandate_objective="balanced_growth_income",
            risk_profile="balanced",
            investment_horizon="medium_term",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            binding_version="7",
            source_record_id="candidate-1",
        )
    )

    assert target.target_weight == Decimal("0.1200000000")
    assert target.min_weight == Decimal("0.0800000000")
    assert target.max_weight is None
    assert member.source_record_id == "portfolio:PB_SG_GLOBAL_BAL_001"
    assert affected_mandate.binding_version == 6
    assert affected_mandate.policy_pack_id == "POLICY_PACK_BALANCED"
    assert candidate.binding_version == 7
    assert candidate.mandate_objective == "balanced_growth_income"


def test_dpm_target_entry_treats_blank_optional_bands_as_absent() -> None:
    target = model_portfolio_target_row(
        SimpleNamespace(
            instrument_id="EQ_US_AAPL",
            target_weight="0.1200000000",
            min_weight=" ",
            max_weight="",
            target_status="active",
            quality_status="accepted",
            source_record_id="target-1",
        )
    )

    assert target.target_weight == Decimal("0.1200000000")
    assert target.min_weight is None
    assert target.max_weight is None


def test_instrument_eligibility_records_map_found_and_missing_rows() -> None:
    found = instrument_eligibility_record(
        SimpleNamespace(
            security_id=" eq_us_aapl ",
            eligibility_status=" approved ",
            product_shelf_status="approved",
            buy_allowed=1,
            sell_allowed=0,
            restriction_reason_codes=["DPM_ALLOWED"],
            settlement_days="2",
            settlement_calendar_id="NYSE",
            liquidity_tier="T1",
            issuer_id="ISSUER_AAPL",
            issuer_name="Apple Inc.",
            ultimate_parent_issuer_id="ISSUER_AAPL",
            ultimate_parent_issuer_name="Apple Inc.",
            asset_class="equity",
            country_of_risk="US",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            quality_status="accepted",
            source_record_id="eligibility-1",
        )
    )
    missing = missing_instrument_eligibility_record(" bond_private_credit_001 ")

    assert found.security_id == "eq_us_aapl"
    assert found.eligibility_status == "APPROVED"
    assert found.product_shelf_status == "APPROVED"
    assert found.buy_allowed is True
    assert found.sell_allowed is False
    assert found.settlement_days == 2
    assert found.quality_status == "ACCEPTED"
    assert missing.security_id == "bond_private_credit_001"
    assert missing.found is False
    assert missing.restriction_reason_codes == ["ELIGIBILITY_PROFILE_MISSING"]
    assert missing.quality_status == "MISSING"


def test_portfolio_tax_lot_record_maps_lot_state_row() -> None:
    lot = portfolio_tax_lot_record(
        PortfolioTaxLotReadRecord(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            security_id=" eq_us_aapl ",
            instrument_id=" EQ_US_AAPL ",
            lot_id="LOT-TXN-BUY-AAPL-001",
            open_quantity="100.0000000000",
            original_quantity="150.0000000000",
            acquisition_date=date(2026, 3, 25),
            lot_cost_base="15005.5000000000",
            lot_cost_local="15005.5000000000",
            source_transaction_id="TXN-BUY-AAPL-001",
            source_system=None,
            calculation_policy_id="BUY_DEFAULT_POLICY",
            calculation_policy_version=None,
            local_currency="USD",
            updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
        )
    )

    assert lot.security_id == "eq_us_aapl"
    assert lot.instrument_id == "EQ_US_AAPL"
    assert lot.open_quantity == Decimal("100.0000000000")
    assert lot.original_quantity == Decimal("150.0000000000")
    assert lot.cost_basis_base == Decimal("15005.5000000000")
    assert lot.tax_lot_status == "OPEN"
    assert lot.local_currency == "USD"
    assert lot.source_lineage == {
        "source_system": "position_lot_state",
        "source_transaction_id": "TXN-BUY-AAPL-001",
        "calculation_policy_id": "BUY_DEFAULT_POLICY",
        "calculation_policy_version": "UNKNOWN",
    }


def test_market_data_coverage_records_map_found_missing_and_stale_rows() -> None:
    as_of_date = date(2026, 5, 31)
    price = market_data_price_coverage_record(
        SimpleNamespace(
            price_date=date(2026, 5, 20),
            price="195.2500000000",
            currency="USD",
        ),
        instrument_id=" EQ_US_AAPL ",
        as_of_date=as_of_date,
        max_staleness_days=5,
    )
    missing_price = missing_market_data_price_coverage_record(" BOND_PRIVATE_CREDIT_001 ")
    fx = market_data_fx_coverage_record(
        SimpleNamespace(
            rate_date=date(2026, 5, 31),
            rate="1.3456000000",
        ),
        from_currency="USD",
        to_currency="SGD",
        as_of_date=as_of_date,
        max_staleness_days=5,
    )
    missing_fx = missing_market_data_fx_coverage_record(
        from_currency="EUR",
        to_currency="SGD",
    )

    assert price.instrument_id == "EQ_US_AAPL"
    assert price.price == Decimal("195.2500000000")
    assert price.age_days == 11
    assert price.quality_status == "STALE"
    assert missing_price.instrument_id == "BOND_PRIVATE_CREDIT_001"
    assert missing_price.found is False
    assert missing_price.quality_status == "MISSING"
    assert fx.rate == Decimal("1.3456000000")
    assert fx.age_days == 0
    assert fx.quality_status == "READY"
    assert missing_fx.from_currency == "EUR"
    assert missing_fx.to_currency == "SGD"
    assert missing_fx.quality_status == "MISSING"


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
