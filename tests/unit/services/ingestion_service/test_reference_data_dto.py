from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from src.services.ingestion_service.app.DTOs.ingestion_validation_errors import (
    DUPLICATE_SOURCE_KEY,
    INVALID_EFFECTIVE_WINDOW,
    INVALID_QUALITY_STATUS,
    INVALID_THRESHOLD_PAIR,
    MISSING_REQUIRED_LINEAGE,
    validate_required_lineage,
)
from src.services.ingestion_service.app.DTOs.reference_data_dto import (
    BenchmarkDefinitionRecord,
    BenchmarkReturnSeriesRecord,
    ClientIncomeNeedsScheduleIngestionRequest,
    ClientIncomeNeedsScheduleRecord,
    ClientRestrictionProfileIngestionRequest,
    ClientRestrictionProfileRecord,
    ClientTaxProfileIngestionRequest,
    ClientTaxProfileRecord,
    ClientTaxRuleSetIngestionRequest,
    ClientTaxRuleSetRecord,
    DiscretionaryMandateBindingIngestionRequest,
    DiscretionaryMandateBindingRecord,
    IndexDefinitionRecord,
    IndexPriceSeriesRecord,
    IndexReturnSeriesRecord,
    InstrumentEligibilityProfileIngestionRequest,
    InstrumentEligibilityProfileRecord,
    LiquidityReserveRequirementIngestionRequest,
    LiquidityReserveRequirementRecord,
    ModelPortfolioDefinitionRecord,
    ModelPortfolioTargetIngestionRequest,
    ModelPortfolioTargetRecord,
    PlannedWithdrawalScheduleIngestionRequest,
    PlannedWithdrawalScheduleRecord,
    RiskFreeSeriesRecord,
    SustainabilityPreferenceProfileIngestionRequest,
    SustainabilityPreferenceProfileRecord,
)


def _target_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
        "model_portfolio_version": "2026.03",
        "instrument_id": "EQ_US_AAPL",
        "target_weight": "0.1200000000",
        "min_weight": "0.0800000000",
        "max_weight": "0.1600000000",
        "target_status": "active",
        "effective_from": "2026-03-25",
    }
    record.update(overrides)
    return record


def _model_portfolio_definition(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
        "model_portfolio_version": "2026.03",
        "display_name": "Singapore Balanced DPM Model",
        "base_currency": "SGD",
        "risk_profile": "balanced",
        "mandate_type": "discretionary",
        "effective_from": "2026-03-25",
    }
    record.update(overrides)
    return record


def _benchmark_definition(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "benchmark_name": "Global Balanced 60/40 Total Return",
        "benchmark_type": "composite",
        "benchmark_currency": "USD",
        "return_convention": "total_return_index",
        "effective_from": "2025-01-01",
    }
    record.update(overrides)
    return record


def _index_definition(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "index_name": "Global Equity Total Return",
        "index_currency": "USD",
        "effective_from": "2026-01-01",
    }
    record.update(overrides)
    return record


def _index_price_series(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "series_id": "series_idx_global_equity_price",
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "series_date": "2026-01-02",
        "index_price": "4567.1234000000",
        "series_currency": "USD",
        "value_convention": "official_close",
    }
    record.update(overrides)
    return record


def _index_return_series(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "series_id": "series_idx_global_equity_return",
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "series_date": "2026-01-02",
        "index_return": "-0.0150000000",
        "return_period": "1d",
        "return_convention": "total_return_index",
        "series_currency": "USD",
    }
    record.update(overrides)
    return record


def _benchmark_return_series(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "series_id": "series_bmk_global_balanced_return",
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "series_date": "2026-01-02",
        "benchmark_return": "-0.0065000000",
        "return_period": "1d",
        "return_convention": "total_return_index",
        "series_currency": "USD",
    }
    record.update(overrides)
    return record


def _risk_free_series(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "series_id": "rf_usd_sofr_3m",
        "risk_free_curve_id": "USD_SOFR_3M",
        "series_date": "2026-01-02",
        "value": "0.0350000000",
        "value_convention": "annualized_rate",
        "series_currency": "USD",
    }
    record.update(overrides)
    return record


def _mandate_binding(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "client_id": "CIF_SG_000184",
        "mandate_type": "discretionary",
        "discretionary_authority_status": "active",
        "booking_center_code": "Singapore",
        "jurisdiction_code": "SG",
        "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
        "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
        "mandate_objective": (
            "Preserve and grow global balanced wealth within controlled drawdown limits."
        ),
        "risk_profile": "balanced",
        "investment_horizon": "long_term",
        "review_cadence": "quarterly",
        "last_review_date": "2026-03-31",
        "next_review_due_date": "2026-06-30",
        "tax_awareness_allowed": True,
        "settlement_awareness_required": True,
        "rebalance_frequency": "monthly",
        "rebalance_bands": {
            "default_band": "0.0250000000",
            "cash_reserve_weight": "0.0200000000",
        },
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _eligibility_profile(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "security_id": "AAPL",
        "eligibility_status": "APPROVED",
        "product_shelf_status": "APPROVED",
        "buy_allowed": True,
        "sell_allowed": True,
        "restriction_reason_codes": [],
        "settlement_days": 2,
        "settlement_calendar_id": "US_NYSE",
        "liquidity_tier": "L1",
        "issuer_id": "APPLE",
        "issuer_name": "Apple Inc.",
        "ultimate_parent_issuer_id": "APPLE_PARENT",
        "ultimate_parent_issuer_name": "Apple Inc.",
        "asset_class": "Equity",
        "country_of_risk": "US",
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _restriction_profile(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "restriction_scope": "asset_class",
        "restriction_code": "NO_PRIVATE_CREDIT_BUY",
        "restriction_status": "active",
        "restriction_source": "client_mandate",
        "asset_classes": ["private_credit"],
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _sustainability_profile(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "preference_framework": "LOTUS_SUSTAINABILITY_V1",
        "preference_code": "MIN_SUSTAINABLE_ALLOCATION",
        "preference_status": "active",
        "preference_source": "client_mandate",
        "minimum_allocation": "0.2000000000",
        "exclusion_codes": ["THERMAL_COAL"],
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _tax_profile(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "tax_profile_id": "TAX_PROFILE_SG_001",
        "tax_residency_country": "SG",
        "booking_tax_jurisdiction": "SG",
        "tax_status": "TAXABLE",
        "profile_status": "active",
        "withholding_tax_rate": "0.1500000000",
        "capital_gains_tax_applicable": False,
        "income_tax_applicable": True,
        "treaty_codes": ["US_SG_TREATY"],
        "eligible_account_types": ["DPM"],
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _tax_rule_set(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "rule_set_id": "TAX_RULES_SG_2026",
        "tax_year": 2026,
        "jurisdiction_code": "SG",
        "rule_code": "US_DIVIDEND_WITHHOLDING",
        "rule_category": "WITHHOLDING",
        "rule_status": "active",
        "rule_source": "bank_tax_reference",
        "applies_to_income_types": ["DIVIDEND"],
        "rate": "0.1500000000",
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _income_needs_schedule(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "schedule_id": "INCOME_NEED_MONTHLY_001",
        "need_type": "LIVING_EXPENSE",
        "need_status": "active",
        "amount": "25000.0000",
        "currency": "SGD",
        "frequency": "MONTHLY",
        "start_date": "2026-04-01",
        "priority": 1,
        "funding_policy": "POLICY_DPM_SG_BALANCED_V1",
    }
    record.update(overrides)
    return record


def _liquidity_reserve_requirement(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "reserve_requirement_id": "RESERVE_MIN_CASH_001",
        "reserve_type": "MIN_CASH_BUFFER",
        "reserve_status": "active",
        "required_amount": "150000.0000",
        "currency": "SGD",
        "horizon_days": 90,
        "priority": 1,
        "policy_source": "POLICY_DPM_SG_BALANCED_V1",
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def _planned_withdrawal_schedule(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "client_id": "CIF_SG_000184",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "withdrawal_schedule_id": "WITHDRAWAL_Q3_001",
        "withdrawal_type": "PLANNED_WITHDRAWAL",
        "withdrawal_status": "active",
        "amount": "50000.0000",
        "currency": "SGD",
        "scheduled_date": "2026-07-15",
        "recurrence_frequency": "QUARTERLY",
        "purpose_code": "CLIENT_SPENDING",
    }
    record.update(overrides)
    return record


def test_model_portfolio_definition_normalizes_base_currency() -> None:
    record = ModelPortfolioDefinitionRecord.model_validate(
        _model_portfolio_definition(base_currency=" sgd ")
    )

    assert record.base_currency == "SGD"


def test_benchmark_definition_normalizes_benchmark_currency() -> None:
    record = BenchmarkDefinitionRecord.model_validate(
        _benchmark_definition(benchmark_currency=" usd ")
    )

    assert record.benchmark_currency == "USD"


def test_reference_data_source_observation_accepts_canonical_lineage_fields() -> None:
    record = BenchmarkDefinitionRecord.model_validate(
        _benchmark_definition(
            source_system="MSCI",
            source_record_id="bmk_v20260131",
            observed_at="2026-01-31T23:00:00Z",
            quality_status=" Accepted ",
        )
    )

    assert record.source_system == "MSCI"
    assert record.observed_at is not None
    assert record.quality_status == "accepted"
    assert record.model_dump(mode="json")["observed_at"] == "2026-01-31T23:00:00Z"
    assert "source_timestamp" not in record.model_dump(mode="json")


def test_reference_data_source_observation_accepts_legacy_lineage_aliases() -> None:
    record = IndexPriceSeriesRecord.model_validate(
        _index_price_series(
            source_vendor="MSCI",
            source_record_id="idxp_20260102",
            source_timestamp="2026-01-02T21:00:00Z",
        )
    )

    assert record.source_system == "MSCI"
    assert record.observed_at is not None
    assert record.model_dump()["source_record_id"] == "idxp_20260102"


def test_reference_data_source_observation_rejects_blank_quality_status() -> None:
    with pytest.raises(ValidationError, match="quality_status must not be blank") as exc_info:
        BenchmarkDefinitionRecord.model_validate(_benchmark_definition(quality_status="  "))

    error = exc_info.value.errors()[0]
    assert error["type"] == INVALID_QUALITY_STATUS
    assert error["ctx"]["field_path"] == "quality_status"


def test_ingestion_validation_taxonomy_returns_missing_lineage_code() -> None:
    class LineageRequiredRecord(BaseModel):
        source_system: str | None = None
        source_record_id: str | None = None
        observed_at: str | None = None

        @model_validator(mode="after")
        def validate_lineage(self) -> "LineageRequiredRecord":
            validate_required_lineage(
                source_system=self.source_system,
                source_record_id=self.source_record_id,
                observed_at=self.observed_at,
            )
            return self

    with pytest.raises(ValidationError) as exc_info:
        LineageRequiredRecord.model_validate({"source_system": "tax-reference"})

    error = exc_info.value.errors()[0]
    assert error["type"] == MISSING_REQUIRED_LINEAGE
    assert error["ctx"]["field_path"] == "source_record_id"
    assert "source_system" in error["ctx"]["remediation"]


@pytest.mark.parametrize(
    ("record_type", "payload", "field_name"),
    [
        (IndexDefinitionRecord, _index_definition(index_currency=" usd "), "index_currency"),
        (
            IndexPriceSeriesRecord,
            _index_price_series(series_currency=" usd "),
            "series_currency",
        ),
        (
            IndexReturnSeriesRecord,
            _index_return_series(series_currency=" usd "),
            "series_currency",
        ),
        (
            BenchmarkReturnSeriesRecord,
            _benchmark_return_series(series_currency=" usd "),
            "series_currency",
        ),
        (RiskFreeSeriesRecord, _risk_free_series(series_currency=" usd "), "series_currency"),
    ],
)
def test_reference_market_series_records_normalize_currency(
    record_type, payload: dict[str, object], field_name: str
) -> None:
    record = record_type.model_validate(payload)

    assert getattr(record, field_name) == "USD"


@pytest.mark.parametrize(
    ("record_type", "payload", "field_name", "expected_currency"),
    [
        (
            ClientTaxRuleSetRecord,
            _tax_rule_set(threshold_amount="250000.0000", threshold_currency=" sgd "),
            "threshold_currency",
            "SGD",
        ),
        (
            ClientIncomeNeedsScheduleRecord,
            _income_needs_schedule(currency=" sgd "),
            "currency",
            "SGD",
        ),
        (
            LiquidityReserveRequirementRecord,
            _liquidity_reserve_requirement(currency=" sgd "),
            "currency",
            "SGD",
        ),
        (
            PlannedWithdrawalScheduleRecord,
            _planned_withdrawal_schedule(currency=" sgd "),
            "currency",
            "SGD",
        ),
    ],
)
def test_private_banking_amount_currency_records_normalize_currency(
    record_type, payload: dict[str, object], field_name: str, expected_currency: str
) -> None:
    record = record_type.model_validate(payload)

    assert getattr(record, field_name) == expected_currency


def test_model_portfolio_target_record_validates_target_band_order() -> None:
    with pytest.raises(ValidationError, match="min_weight must be less than or equal"):
        ModelPortfolioTargetRecord.model_validate(_target_record(min_weight="0.1300000000"))

    with pytest.raises(ValidationError, match="max_weight must be greater than or equal"):
        ModelPortfolioTargetRecord.model_validate(_target_record(max_weight="0.1100000000"))


def test_model_portfolio_target_ingestion_request_rejects_duplicate_targets() -> None:
    duplicate = _target_record()

    with pytest.raises(ValidationError, match="duplicate target records"):
        ModelPortfolioTargetIngestionRequest.model_validate(
            {"model_portfolio_targets": [duplicate, dict(duplicate)]}
        )


def test_model_portfolio_target_ingestion_request_accepts_distinct_instruments() -> None:
    request = ModelPortfolioTargetIngestionRequest.model_validate(
        {
            "model_portfolio_targets": [
                _target_record(instrument_id="EQ_US_AAPL"),
                _target_record(instrument_id="FI_US_TREASURY_10Y"),
            ]
        }
    )

    assert [target.instrument_id for target in request.model_portfolio_targets] == [
        "EQ_US_AAPL",
        "FI_US_TREASURY_10Y",
    ]


def test_mandate_binding_record_validates_effective_window() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after"):
        DiscretionaryMandateBindingRecord.model_validate(
            _mandate_binding(effective_from="2026-04-10", effective_to="2026-04-01")
        )


def test_mandate_binding_ingestion_rejects_duplicate_effective_bindings() -> None:
    duplicate = _mandate_binding()

    with pytest.raises(ValidationError, match="duplicate binding records"):
        DiscretionaryMandateBindingIngestionRequest.model_validate(
            {"mandate_bindings": [duplicate, dict(duplicate)]}
        )


def test_mandate_binding_ingestion_accepts_versioned_corrections() -> None:
    request = DiscretionaryMandateBindingIngestionRequest.model_validate(
        {
            "mandate_bindings": [
                _mandate_binding(binding_version=1),
                _mandate_binding(binding_version=2),
            ]
        }
    )

    assert [binding.binding_version for binding in request.mandate_bindings] == [1, 2]


def test_instrument_eligibility_profile_rejects_invalid_effective_window() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after"):
        InstrumentEligibilityProfileRecord.model_validate(
            _eligibility_profile(effective_from="2026-04-10", effective_to="2026-04-01")
        )


def test_instrument_eligibility_profile_rejects_banned_buy_or_sell_flags() -> None:
    with pytest.raises(ValidationError, match="buy_allowed must be false"):
        InstrumentEligibilityProfileRecord.model_validate(
            _eligibility_profile(product_shelf_status="BANNED", buy_allowed=True)
        )

    with pytest.raises(ValidationError, match="sell_allowed must be false"):
        InstrumentEligibilityProfileRecord.model_validate(
            _eligibility_profile(
                product_shelf_status="BANNED",
                eligibility_status="BANNED",
                buy_allowed=False,
                sell_allowed=True,
            )
        )


def test_instrument_eligibility_ingestion_rejects_duplicate_effective_profiles() -> None:
    duplicate = _eligibility_profile()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        InstrumentEligibilityProfileIngestionRequest.model_validate(
            {"eligibility_profiles": [duplicate, dict(duplicate)]}
        )


def test_client_restriction_profile_requires_scope_values_for_scoped_restrictions() -> None:
    with pytest.raises(ValidationError, match="scoped restrictions"):
        ClientRestrictionProfileRecord.model_validate(
            _restriction_profile(restriction_scope="issuer", asset_classes=[])
        )


def test_client_restriction_profile_ingestion_rejects_duplicate_effective_profiles() -> None:
    duplicate = _restriction_profile()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        ClientRestrictionProfileIngestionRequest.model_validate(
            {"restriction_profiles": [duplicate, dict(duplicate)]}
        )


def test_sustainability_preference_profile_validates_bounds_and_substance() -> None:
    with pytest.raises(ValidationError, match="minimum_allocation"):
        SustainabilityPreferenceProfileRecord.model_validate(
            _sustainability_profile(
                minimum_allocation="0.3000000000",
                maximum_allocation="0.2000000000",
            )
        )

    with pytest.raises(ValidationError, match="exclusion, tilt, or allocation"):
        SustainabilityPreferenceProfileRecord.model_validate(
            _sustainability_profile(
                minimum_allocation=None,
                exclusion_codes=[],
                positive_tilt_codes=[],
            )
        )


def test_sustainability_preference_ingestion_rejects_duplicate_effective_profiles() -> None:
    duplicate = _sustainability_profile()

    with pytest.raises(ValidationError, match="duplicate effective records") as exc_info:
        SustainabilityPreferenceProfileIngestionRequest.model_validate(
            {"sustainability_preferences": [duplicate, dict(duplicate)]}
        )

    assert exc_info.value.errors()[0]["type"] == DUPLICATE_SOURCE_KEY


def test_client_tax_profile_validates_unknown_status_has_no_tax_detail() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN tax_status"):
        ClientTaxProfileRecord.model_validate(
            _tax_profile(
                tax_status="UNKNOWN",
                withholding_tax_rate="0.1500000000",
                income_tax_applicable=True,
            )
        )


def test_client_tax_profile_ingestion_rejects_duplicate_effective_profiles() -> None:
    duplicate = _tax_profile()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        ClientTaxProfileIngestionRequest.model_validate(
            {"tax_profiles": [duplicate, dict(duplicate)]}
        )


def test_client_tax_rule_set_validates_threshold_pair_and_substance() -> None:
    with pytest.raises(ValidationError, match="threshold_currency is required") as exc_info:
        ClientTaxRuleSetRecord.model_validate(_tax_rule_set(threshold_amount="250000.0000"))
    assert exc_info.value.errors()[0]["type"] == INVALID_THRESHOLD_PAIR

    with pytest.raises(ValidationError, match="threshold_amount is required"):
        ClientTaxRuleSetRecord.model_validate(
            _tax_rule_set(threshold_amount=None, threshold_currency="SGD")
        )

    with pytest.raises(ValidationError, match="bounded rule evidence"):
        ClientTaxRuleSetRecord.model_validate(
            _tax_rule_set(
                applies_to_asset_classes=[],
                applies_to_security_ids=[],
                applies_to_income_types=[],
                rate=None,
                threshold_amount=None,
                threshold_currency=None,
            )
        )


def test_client_tax_rule_set_validates_effective_window() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after") as exc_info:
        ClientTaxRuleSetRecord.model_validate(
            _tax_rule_set(effective_from="2026-04-10", effective_to="2026-04-01")
        )

    error = exc_info.value.errors()[0]
    assert error["type"] == INVALID_EFFECTIVE_WINDOW
    assert error["ctx"]["field_path"] == "effective_to"


def test_client_tax_rule_set_ingestion_rejects_duplicate_effective_rules() -> None:
    duplicate = _tax_rule_set()

    with pytest.raises(ValidationError, match="duplicate effective records") as exc_info:
        ClientTaxRuleSetIngestionRequest.model_validate(
            {"tax_rule_sets": [duplicate, dict(duplicate)]}
        )

    assert exc_info.value.errors()[0]["type"] == DUPLICATE_SOURCE_KEY


def test_client_income_needs_schedule_validates_effective_window() -> None:
    with pytest.raises(ValidationError, match="end_date must be on or after"):
        ClientIncomeNeedsScheduleRecord.model_validate(
            _income_needs_schedule(start_date="2026-04-10", end_date="2026-04-01")
        )


def test_client_income_needs_schedule_ingestion_rejects_duplicate_rows() -> None:
    duplicate = _income_needs_schedule()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        ClientIncomeNeedsScheduleIngestionRequest.model_validate(
            {"income_needs_schedules": [duplicate, dict(duplicate)]}
        )


def test_liquidity_reserve_requirement_validates_effective_window() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after"):
        LiquidityReserveRequirementRecord.model_validate(
            _liquidity_reserve_requirement(
                effective_from="2026-04-10",
                effective_to="2026-04-01",
            )
        )


def test_liquidity_reserve_requirement_ingestion_rejects_duplicate_rows() -> None:
    duplicate = _liquidity_reserve_requirement()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        LiquidityReserveRequirementIngestionRequest.model_validate(
            {"liquidity_reserve_requirements": [duplicate, dict(duplicate)]}
        )


def test_planned_withdrawal_schedule_ingestion_rejects_duplicate_rows() -> None:
    duplicate = _planned_withdrawal_schedule()

    with pytest.raises(ValidationError, match="duplicate effective records"):
        PlannedWithdrawalScheduleIngestionRequest.model_validate(
            {"planned_withdrawal_schedules": [duplicate, dict(duplicate)]}
        )


def test_planned_withdrawal_schedule_record_accepts_bounded_record() -> None:
    record = PlannedWithdrawalScheduleRecord.model_validate(_planned_withdrawal_schedule())

    assert record.withdrawal_schedule_id == "WITHDRAWAL_Q3_001"
