from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.reference_data_mappers import (
    benchmark_definition_response,
    cio_model_change_affected_mandate,
    client_income_needs_schedule_entry,
    client_restriction_profile_entry,
    client_tax_profile_entry,
    client_tax_rule_set_entry,
    dpm_portfolio_universe_candidate,
    index_definition_response,
    instrument_eligibility_record,
    liquidity_reserve_requirement_entry,
    missing_instrument_eligibility_record,
    model_portfolio_target_row,
    planned_withdrawal_schedule_entry,
    portfolio_manager_book_member,
    sustainability_preference_profile_entry,
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


def test_client_tax_entries_map_source_data_rows() -> None:
    tax_profile = client_tax_profile_entry(
        SimpleNamespace(
            tax_profile_id="TAX_PROFILE_SG_001",
            tax_residency_country="SG",
            booking_tax_jurisdiction="SG",
            tax_status="resident",
            profile_status="active",
            withholding_tax_rate="0.3000000000",
            capital_gains_tax_applicable=False,
            income_tax_applicable=True,
            treaty_codes=["US_SG_DTA", ""],
            eligible_account_types=["DPM", "ADVISORY"],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            profile_version="2",
            source_record_id="tax-profile-1",
        )
    )
    tax_rule = client_tax_rule_set_entry(
        SimpleNamespace(
            rule_set_id="TAX_RULES_SG_2026",
            tax_year="2026",
            jurisdiction_code="SG",
            rule_code="US_DIVIDEND_WITHHOLDING",
            rule_category="withholding",
            rule_status="active",
            rule_source="tax_policy",
            applies_to_asset_classes=["equity"],
            applies_to_security_ids=["EQ_US_AAPL"],
            applies_to_income_types=["dividend"],
            rate="0.3000000000",
            threshold_amount="250000.0000",
            threshold_currency="USD",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            rule_version="3",
            source_record_id="tax-rule-1",
        )
    )

    assert tax_profile.withholding_tax_rate == Decimal("0.3000000000")
    assert tax_profile.treaty_codes == ["US_SG_DTA"]
    assert tax_profile.profile_version == 2
    assert tax_rule.tax_year == 2026
    assert tax_rule.rate == Decimal("0.3000000000")
    assert tax_rule.threshold_amount == Decimal("250000.0000")


def test_client_liquidity_entries_map_source_data_rows() -> None:
    income = client_income_needs_schedule_entry(
        SimpleNamespace(
            schedule_id="INCOME_NEED_MONTHLY_001",
            need_type="monthly_income",
            need_status="active",
            amount="12000.0000",
            currency="SGD",
            frequency="monthly",
            start_date=date(2026, 1, 1),
            end_date=None,
            priority="1",
            funding_policy="cash_first",
            source_record_id="income-1",
        )
    )
    reserve = liquidity_reserve_requirement_entry(
        SimpleNamespace(
            reserve_requirement_id="RESERVE_MIN_CASH_001",
            reserve_type="minimum_cash",
            reserve_status="active",
            required_amount="50000.0000",
            currency="SGD",
            horizon_days="90",
            priority="2",
            policy_source="investment_policy_statement",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            requirement_version="4",
            source_record_id="reserve-1",
        )
    )
    withdrawal = planned_withdrawal_schedule_entry(
        SimpleNamespace(
            withdrawal_schedule_id="WITHDRAWAL_Q3_001",
            withdrawal_type="planned_spending",
            withdrawal_status="active",
            amount="25000.0000",
            currency="SGD",
            scheduled_date=date(2026, 7, 15),
            recurrence_frequency="quarterly",
            purpose_code="education",
            source_record_id="withdrawal-1",
        )
    )

    assert income.amount == Decimal("12000.0000")
    assert income.priority == 1
    assert reserve.required_amount == Decimal("50000.0000")
    assert reserve.requirement_version == 4
    assert withdrawal.amount == Decimal("25000.0000")
    assert withdrawal.purpose_code == "education"


def test_client_governance_entries_map_source_data_rows() -> None:
    restriction = client_restriction_profile_entry(
        SimpleNamespace(
            restriction_scope="issuer",
            restriction_code="NO_PRIVATE_CREDIT_BUY",
            restriction_status="active",
            restriction_source="investment_policy_statement",
            applies_to_buy=True,
            applies_to_sell=False,
            instrument_ids=["BOND_PRIVATE_CREDIT_001", ""],
            asset_classes=["private_credit"],
            issuer_ids=["ISSUER_001"],
            country_codes=["US"],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            restriction_version="5",
            source_record_id="restriction-1",
        )
    )
    preference = sustainability_preference_profile_entry(
        SimpleNamespace(
            preference_framework="LOTUS_SUSTAINABILITY_V1",
            preference_code="MIN_SUSTAINABLE_ALLOCATION",
            preference_status="active",
            preference_source="client_suitability",
            minimum_allocation="0.2000000000",
            maximum_allocation=None,
            applies_to_asset_classes=["equity", ""],
            exclusion_codes=["THERMAL_COAL"],
            positive_tilt_codes=["GREEN_REVENUE"],
            effective_from=date(2026, 1, 1),
            effective_to=None,
            preference_version="3",
            source_record_id="preference-1",
        )
    )

    assert restriction.applies_to_buy is True
    assert restriction.applies_to_sell is False
    assert restriction.instrument_ids == ["BOND_PRIVATE_CREDIT_001"]
    assert restriction.restriction_version == 5
    assert preference.minimum_allocation == Decimal("0.2000000000")
    assert preference.maximum_allocation is None
    assert preference.applies_to_asset_classes == ["equity"]
    assert preference.preference_version == 3
