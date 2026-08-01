"""Golden tests for explicit position-valuation representations and outputs."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext

import pytest
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output
from portfolio_common.domain.financial.precision import (
    DecimalPrecisionError,
    DecimalPrecisionViolation,
)
from portfolio_common.domain.valuation import (
    AccruedIncomeTreatment,
    FinancialSourceReference,
    FxConversionPolicy,
    PositionScaling,
    PositionValuationEconomicInputs,
    PositionValuationEvidence,
    PositionValuationInputs,
    PositionValuationPolicy,
    PrincipalBasis,
    UnsupportedValuationError,
    ValuationInputBasis,
    ValuationOutputMeasure,
    build_calculation_lineage,
    calculate_position_valuation,
    calculate_position_valuation_local_economics,
    canonical_content_hash,
)


def _policy(
    *,
    input_basis: ValuationInputBasis,
    principal_basis: PrincipalBasis = PrincipalBasis.POSITION_UNITS,
    scaling: PositionScaling = PositionScaling.QUANTITY,
    accrued: AccruedIncomeTreatment = AccruedIncomeTreatment.NOT_APPLICABLE,
    fx: FxConversionPolicy = FxConversionPolicy.ALREADY_IN_REPORTING_CURRENCY,
    output: ValuationOutputMeasure = ValuationOutputMeasure.MARKET_VALUE,
    denominator: Decimal | None = None,
) -> PositionValuationPolicy:
    return PositionValuationPolicy(
        policy_id="GOLDEN_POLICY",
        policy_version=1,
        input_basis=input_basis,
        principal_basis=principal_basis,
        position_scaling=scaling,
        accrued_income_treatment=accrued,
        fx_conversion=fx,
        output_measure=output,
        quote_denominator=denominator,
    )


def _inputs(**overrides: object) -> PositionValuationInputs:
    values: dict[str, object] = {
        "source_value": Decimal("32.50"),
        "signed_quantity": Decimal("125"),
        "source_currency": "USD",
        "reporting_currency": "USD",
        "evidence": _evidence(),
    }
    values.update(overrides)
    return PositionValuationInputs(**values)  # type: ignore[arg-type]


def _source(fact: str, revision: str = "revision-1") -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="valuation_fixture",
        source_record_id=f"POSITION-001:{fact}",
        source_revision=revision,
        source_content_hash=canonical_content_hash({"fact": fact, "revision": revision}),
        observed_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
    )


def _evidence(**overrides: object) -> PositionValuationEvidence:
    calculated_accrual = build_calculation_lineage(
        algorithm_id="SEGMENTED_GROSS_CONTRACTUAL_ACCRUAL",
        algorithm_version=2,
        intermediate_precision=50,
        input_payload={"schedule": "fixture"},
        output_payload={"gross_accrued_income": Decimal("12500")},
    )
    values: dict[str, object] = {
        "policy_assignment": _source("policy_assignment"),
        "source_value": _source("source_value"),
        "source_currency": _source("source_currency"),
        "reporting_currency": _source("reporting_currency"),
        "signed_quantity": _source("signed_quantity"),
        "signed_face_amount": _source("signed_face_amount"),
        "principal_factor": _source("principal_factor"),
        "signed_current_principal": _source("signed_current_principal"),
        "contract_multiplier": _source("contract_multiplier"),
        "calculated_accrued_income": calculated_accrual,
        "supplied_accrued_income": _source("supplied_accrued_income"),
        "direct_source_to_reporting_fx_rate": _source("fx_rate"),
    }
    values.update(overrides)
    return PositionValuationEvidence(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "input_basis",
    [ValuationInputBasis.UNIT_PRICE, ValuationInputBasis.NAV_PER_UNIT],
)
def test_unit_price_and_nav_are_scaled_by_position_units(
    input_basis: ValuationInputBasis,
) -> None:
    result = calculate_position_valuation(
        policy=_policy(input_basis=input_basis),
        inputs=_inputs(),
    )

    assert result.clean_value_local is None
    assert result.total_market_value_local == Decimal("4062.50")
    assert result.notional_exposure_local is None
    assert result.lineage.algorithm_id == "POSITION_VALUATION_SCALING"
    assert result.lineage.algorithm_version == 2
    assert result.lineage.intermediate_precision == 64
    assert result.lineage.numeric_output_policy is not None
    assert (
        result.lineage.numeric_output_policy.policy_id == "position-valuation-ledger-output@1.0.0"
    )


def test_local_economics_matches_lineaged_unit_price_result() -> None:
    policy = _policy(input_basis=ValuationInputBasis.UNIT_PRICE)

    economics = calculate_position_valuation_local_economics(
        policy=policy,
        inputs=PositionValuationEconomicInputs(
            source_value=Decimal("32.50"),
            signed_quantity=Decimal("125"),
        ),
    )
    result = calculate_position_valuation(policy=policy, inputs=_inputs())

    assert economics.total_market_value_local == result.total_market_value_local
    assert economics.clean_value_local is result.clean_value_local is None
    assert economics.current_principal is result.current_principal is None
    assert economics.lineage.algorithm_id == "POSITION_VALUATION_LOCAL_ECONOMICS_NORMALIZATION"
    assert economics.lineage.algorithm_version == 1
    assert economics.lineage.numeric_output_policy is not None
    assert (
        economics.lineage.numeric_output_policy.policy_id
        == "position-valuation-ledger-output@1.0.0"
    )


def test_local_economics_normalizes_explicit_face_principal_without_evidence() -> None:
    economics = calculate_position_valuation_local_economics(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
            denominator=Decimal("100"),
        ),
        inputs=PositionValuationEconomicInputs(
            source_value=Decimal("99.25"),
            signed_quantity=Decimal("1000000"),
            signed_face_amount=Decimal("1000000"),
        ),
    )

    assert economics.current_principal == Decimal("1000000.0000000000")
    assert economics.total_market_value_local == Decimal("992500.0000000000")
    assert economics.clean_value_local is None
    assert economics.accrued_income_local is None
    assert calculation_lineage_binds_output(
        economics.lineage,
        output_payload={
            "accrued_income_local": economics.accrued_income_local,
            "clean_value_local": economics.clean_value_local,
            "current_principal": economics.current_principal,
            "notional_exposure_local": economics.notional_exposure_local,
            "settlement_variation_local": economics.settlement_variation_local,
            "total_market_value_local": economics.total_market_value_local,
        },
    )


def test_position_lineage_changes_on_source_revision_even_when_value_is_equal() -> None:
    policy = _policy(
        input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
        scaling=PositionScaling.NONE,
    )
    baseline_inputs = _inputs(source_value=Decimal("100"))
    revised_inputs = replace(
        baseline_inputs,
        evidence=replace(
            baseline_inputs.evidence,
            source_value=_source("source_value", "revision-2"),
        ),
    )

    baseline = calculate_position_valuation(policy=policy, inputs=baseline_inputs)
    revised = calculate_position_valuation(policy=policy, inputs=revised_inputs)

    assert revised.total_market_value_local == baseline.total_market_value_local
    assert revised.lineage.input_content_hash != baseline.lineage.input_content_hash
    assert revised.lineage.calculation_content_hash != baseline.lineage.calculation_content_hash
    assert revised.lineage.output_content_hash != baseline.lineage.output_content_hash


def test_position_calculation_is_independent_of_ambient_decimal_precision() -> None:
    policy = _policy(
        input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        principal_basis=PrincipalBasis.FACE_AMOUNT,
        scaling=PositionScaling.PRINCIPAL,
        denominator=Decimal("3"),
    )
    inputs = _inputs(source_value=Decimal("1"), signed_face_amount=Decimal("1"))

    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        low_precision = calculate_position_valuation(policy=policy, inputs=inputs)
    with localcontext() as context:
        context.prec = 38
        context.rounding = ROUND_UP
        high_precision = calculate_position_valuation(policy=policy, inputs=inputs)

    assert high_precision == low_precision


def test_clean_percent_of_principal_adds_separate_accrued_income_once() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.CALCULATED_SEPARATELY,
            denominator=Decimal("100"),
        ),
        inputs=_inputs(
            source_value=Decimal("101.25"),
            signed_face_amount=Decimal("1000000"),
            calculated_accrued_income=Decimal("12500"),
        ),
    )

    assert result.current_principal == Decimal("1000000")
    assert result.clean_value_local == Decimal("1012500.00")
    assert result.accrued_income_local == Decimal("12500")
    assert result.total_market_value_local == Decimal("1025000.00")


def test_dirty_factor_based_value_uses_current_principal_without_double_accrual() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
            principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
            denominator=Decimal("100"),
        ),
        inputs=_inputs(
            source_value=Decimal("99.50"),
            signed_face_amount=Decimal("1000000"),
            principal_factor=Decimal("0.72"),
        ),
    )

    assert result.current_principal == Decimal("720000.00")
    assert result.clean_value_local is None
    assert result.accrued_income_local is None
    assert result.total_market_value_local == Decimal("716400.0000")


def test_zero_coupon_policy_has_explicit_no_periodic_accrual() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.NO_PERIODIC_ACCRUAL,
            denominator=Decimal("100"),
        ),
        inputs=_inputs(
            source_value=Decimal("82.75"),
            signed_face_amount=Decimal("1000000"),
        ),
    )

    assert result.clean_value_local == Decimal("827500.00")
    assert result.accrued_income_local is None
    assert result.total_market_value_local == result.clean_value_local


def test_clean_ex_coupon_policy_adds_signed_rebate_interest_once() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.CALCULATED_EX_COUPON_SEPARATELY,
            denominator=Decimal("100"),
        ),
        inputs=_inputs(
            source_value=Decimal("101.25"),
            signed_face_amount=Decimal("1000000"),
            calculated_accrued_income=Decimal(
                "-994.4751381215469613259668508287292817679558011050"
            ),
        ),
    )

    assert result.clean_value_local == Decimal("1012500.00")
    assert result.accrued_income_local == Decimal("-994.4751381215")
    assert result.total_market_value_local == Decimal("1011505.5248618785")


def test_clean_value_and_accrual_round_before_reconciled_total() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
            accrued=AccruedIncomeTreatment.CALCULATED_SEPARATELY,
            denominator=Decimal("100"),
        ),
        inputs=_inputs(
            source_value=Decimal("100"),
            signed_face_amount=Decimal("0.00000000005"),
            calculated_accrued_income=Decimal("0.00000000005"),
        ),
    )

    assert result.clean_value_local == Decimal("0E-10")
    assert result.accrued_income_local == Decimal("0E-10")
    assert result.total_market_value_local == Decimal("0E-10")
    assert result.total_market_value_local == (
        result.clean_value_local + result.accrued_income_local
    )


def test_per_underlying_unit_and_per_contract_values_are_not_double_scaled() -> None:
    per_unit = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT,
            scaling=PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
        ),
        inputs=_inputs(
            source_value=Decimal("2.25"),
            signed_quantity=Decimal("3"),
            contract_multiplier=Decimal("100"),
        ),
    )
    per_contract = calculate_position_valuation(
        policy=_policy(input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_PER_CONTRACT),
        inputs=_inputs(source_value=Decimal("225"), signed_quantity=Decimal("3")),
    )

    assert per_unit.total_market_value_local == Decimal("675.00")
    assert per_contract.total_market_value_local == Decimal("675")


def test_whole_position_fair_value_is_not_scaled_and_can_represent_a_liability() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
            scaling=PositionScaling.NONE,
        ),
        inputs=_inputs(source_value=Decimal("-12500"), signed_quantity=Decimal("300")),
    )

    assert result.total_market_value_local == Decimal("-12500")


def test_position_valuation_fails_before_persistence_on_output_magnitude_overflow() -> None:
    with pytest.raises(DecimalPrecisionError) as exc_info:
        calculate_position_valuation(
            policy=_policy(
                input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
                scaling=PositionScaling.NONE,
            ),
            inputs=_inputs(source_value=Decimal("100000000")),
        )

    assert exc_info.value.violation is DecimalPrecisionViolation.MAGNITUDE_OVERFLOW
    assert exc_info.value.policy_name == "position-valuation-ledger-output@1.0.0"


def test_futures_contract_value_populates_notional_but_never_market_value() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT,
            scaling=PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
            output=ValuationOutputMeasure.NOTIONAL_EXPOSURE,
        ),
        inputs=_inputs(
            source_value=Decimal("5200"),
            signed_quantity=Decimal("2"),
            contract_multiplier=Decimal("50"),
        ),
    )

    assert result.notional_exposure_local == Decimal("520000")
    assert result.total_market_value_local is None


def test_supplied_settlement_variation_remains_separate_from_market_value() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION,
            scaling=PositionScaling.NONE,
            output=ValuationOutputMeasure.SETTLEMENT_VARIATION,
        ),
        inputs=_inputs(source_value=Decimal("-2500")),
    )

    assert result.settlement_variation_local == Decimal("-2500")
    assert result.total_market_value_local is None
    assert result.notional_exposure_local is None


def test_direct_fx_conversion_applies_only_the_supplied_direction() -> None:
    result = calculate_position_valuation(
        policy=_policy(
            input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
            scaling=PositionScaling.NONE,
            fx=FxConversionPolicy.DIRECT_SOURCE_TO_REPORTING,
        ),
        inputs=_inputs(
            source_value=Decimal("100"),
            reporting_currency="SGD",
            direct_source_to_reporting_fx_rate=Decimal("1.35"),
        ),
    )

    assert result.source_to_reporting_fx_rate == Decimal("1.35")
    assert result.total_market_value_reporting == Decimal("135.00")


@pytest.mark.parametrize(
    ("policy", "inputs", "message"),
    [
        (
            _policy(
                input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
                principal_basis=PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL,
                scaling=PositionScaling.PRINCIPAL,
                denominator=Decimal("100"),
            ),
            _inputs(source_value=Decimal("101"), signed_face_amount=Decimal("1000")),
            "principal_factor is required",
        ),
        (
            _policy(
                input_basis=ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT,
                scaling=PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
            ),
            _inputs(source_value=Decimal("2"), signed_quantity=Decimal("3")),
            "contract_multiplier is required",
        ),
        (
            _policy(
                input_basis=ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION,
                scaling=PositionScaling.NONE,
                fx=FxConversionPolicy.DIRECT_SOURCE_TO_REPORTING,
            ),
            _inputs(source_value=Decimal("100"), reporting_currency="SGD"),
            "direct_source_to_reporting_fx_rate is required",
        ),
    ],
)
def test_missing_authoritative_inputs_fail_closed(
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
    message: str,
) -> None:
    with pytest.raises(UnsupportedValuationError, match=message):
        calculate_position_valuation(policy=policy, inputs=inputs)


def test_missing_consumed_source_evidence_fails_closed() -> None:
    inputs = _inputs()
    incomplete_evidence = replace(inputs.evidence, signed_quantity=None)

    with pytest.raises(UnsupportedValuationError, match="signed_quantity evidence"):
        calculate_position_valuation(
            policy=_policy(input_basis=ValuationInputBasis.UNIT_PRICE),
            inputs=replace(inputs, evidence=incomplete_evidence),
        )


def test_local_economics_lineage_binds_distinct_source_inputs_with_equal_output() -> None:
    policy = _policy(input_basis=ValuationInputBasis.UNIT_PRICE)
    first = calculate_position_valuation_local_economics(
        policy=policy,
        inputs=PositionValuationEconomicInputs(
            source_value=Decimal("2"),
            signed_quantity=Decimal("50"),
        ),
    )
    second = calculate_position_valuation_local_economics(
        policy=policy,
        inputs=PositionValuationEconomicInputs(
            source_value=Decimal("4"),
            signed_quantity=Decimal("25"),
        ),
    )

    assert first.total_market_value_local == second.total_market_value_local == Decimal("100")
    assert first.lineage.input_content_hash != second.lineage.input_content_hash
    assert first.lineage.calculation_content_hash != second.lineage.calculation_content_hash
    assert first.lineage.output_content_hash != second.lineage.output_content_hash


def test_invalid_policy_combinations_are_rejected_before_calculation() -> None:
    with pytest.raises(ValueError, match="positive quote_denominator"):
        _policy(
            input_basis=ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
            principal_basis=PrincipalBasis.FACE_AMOUNT,
            scaling=PositionScaling.PRINCIPAL,
        )
    with pytest.raises(ValueError, match="cannot populate market value"):
        _policy(
            input_basis=ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION,
            scaling=PositionScaling.NONE,
        )
    with pytest.raises(ValueError, match="clean percent-of-principal"):
        _policy(
            input_basis=ValuationInputBasis.UNIT_PRICE,
            accrued=AccruedIncomeTreatment.CALCULATED_EX_COUPON_SEPARATELY,
        )
