"""Explicit, composable policies for supplied position-valuation facts.

The calculator normalizes and scales authoritative source values. It deliberately does
not price securities, infer quote conventions, forecast rates, or derive derivative MTM.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum

from .calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    build_calculation_lineage,
)


class UnsupportedValuationError(ValueError):
    """Raised when supplied facts cannot support the declared valuation policy."""


POSITION_VALUATION_ALGORITHM_ID = "POSITION_VALUATION_SCALING"
POSITION_VALUATION_ALGORITHM_VERSION = 1
POSITION_VALUATION_INTERMEDIATE_PRECISION = 50


class ValuationInputBasis(StrEnum):
    """Representation of the authoritative source value."""

    UNIT_PRICE = "UNIT_PRICE"
    NAV_PER_UNIT = "NAV_PER_UNIT"
    PERCENT_OF_PRINCIPAL_CLEAN = "PERCENT_OF_PRINCIPAL_CLEAN"
    PERCENT_OF_PRINCIPAL_DIRTY = "PERCENT_OF_PRINCIPAL_DIRTY"
    SUPPLIED_VALUE_PER_UNDERLYING_UNIT = "SUPPLIED_VALUE_PER_UNDERLYING_UNIT"
    SUPPLIED_FAIR_VALUE_PER_CONTRACT = "SUPPLIED_FAIR_VALUE_PER_CONTRACT"
    SUPPLIED_FAIR_VALUE_WHOLE_POSITION = "SUPPLIED_FAIR_VALUE_WHOLE_POSITION"
    SETTLEMENT_VARIATION_WHOLE_POSITION = "SETTLEMENT_VARIATION_WHOLE_POSITION"


class PrincipalBasis(StrEnum):
    """Quantity or principal fact used by the scaling policy."""

    POSITION_UNITS = "POSITION_UNITS"
    FACE_AMOUNT = "FACE_AMOUNT"
    FACTOR_ADJUSTED_CURRENT_PRINCIPAL = "FACTOR_ADJUSTED_CURRENT_PRINCIPAL"
    SUPPLIED_CURRENT_PRINCIPAL = "SUPPLIED_CURRENT_PRINCIPAL"


class PositionScaling(StrEnum):
    """Scaling applied exactly once to the source value."""

    NONE = "NONE"
    QUANTITY = "QUANTITY"
    PRINCIPAL = "PRINCIPAL"
    CONTRACT_COUNT_AND_MULTIPLIER = "CONTRACT_COUNT_AND_MULTIPLIER"


class AccruedIncomeTreatment(StrEnum):
    """How accrued income relates to the supplied value."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_PERIODIC_ACCRUAL = "NO_PERIODIC_ACCRUAL"
    INCLUDED_IN_SOURCE_VALUE = "INCLUDED_IN_SOURCE_VALUE"
    CALCULATED_SEPARATELY = "CALCULATED_SEPARATELY"
    CALCULATED_EX_COUPON_SEPARATELY = "CALCULATED_EX_COUPON_SEPARATELY"
    SUPPLIED_SEPARATELY = "SUPPLIED_SEPARATELY"


class FxConversionPolicy(StrEnum):
    """Permitted source-to-reporting currency conversion behavior."""

    ALREADY_IN_REPORTING_CURRENCY = "ALREADY_IN_REPORTING_CURRENCY"
    DIRECT_SOURCE_TO_REPORTING = "DIRECT_SOURCE_TO_REPORTING"


class ValuationOutputMeasure(StrEnum):
    """Economic measure populated by the calculation."""

    MARKET_VALUE = "MARKET_VALUE"
    NOTIONAL_EXPOSURE = "NOTIONAL_EXPOSURE"
    SETTLEMENT_VARIATION = "SETTLEMENT_VARIATION"


_PERCENT_OF_PRINCIPAL_BASES = {
    ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN,
    ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY,
}
_PER_UNIT_BASES = {
    ValuationInputBasis.UNIT_PRICE,
    ValuationInputBasis.NAV_PER_UNIT,
}


@dataclass(frozen=True, slots=True)
class PositionValuationPolicy:
    """One explicit composition of representation and scaling policies."""

    policy_id: str
    policy_version: int
    input_basis: ValuationInputBasis
    principal_basis: PrincipalBasis
    position_scaling: PositionScaling
    accrued_income_treatment: AccruedIncomeTreatment
    fx_conversion: FxConversionPolicy
    output_measure: ValuationOutputMeasure = ValuationOutputMeasure.MARKET_VALUE
    quote_denominator: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be nonblank")
        if self.policy_version < 1:
            raise ValueError("policy_version must be positive")
        self._validate_representation_scaling()
        self._validate_output_measure()
        self._validate_accrued_income_treatment()

    def _validate_representation_scaling(self) -> None:
        if self.input_basis in _PERCENT_OF_PRINCIPAL_BASES:
            if self.position_scaling is not PositionScaling.PRINCIPAL:
                raise ValueError("percent-of-principal values require PRINCIPAL scaling")
            if self.principal_basis is PrincipalBasis.POSITION_UNITS:
                raise ValueError("percent-of-principal values require an explicit principal basis")
            if self.quote_denominator is None or self.quote_denominator <= 0:
                raise ValueError("percent-of-principal values require a positive quote_denominator")
            return

        if self.principal_basis is not PrincipalBasis.POSITION_UNITS:
            raise ValueError("non-principal scaling requires POSITION_UNITS principal basis")
        if self.quote_denominator is not None:
            raise ValueError("quote_denominator is valid only for percent-of-principal values")
        expected_scaling = {
            ValuationInputBasis.UNIT_PRICE: PositionScaling.QUANTITY,
            ValuationInputBasis.NAV_PER_UNIT: PositionScaling.QUANTITY,
            ValuationInputBasis.SUPPLIED_VALUE_PER_UNDERLYING_UNIT: (
                PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER
            ),
            ValuationInputBasis.SUPPLIED_FAIR_VALUE_PER_CONTRACT: PositionScaling.QUANTITY,
            ValuationInputBasis.SUPPLIED_FAIR_VALUE_WHOLE_POSITION: PositionScaling.NONE,
            ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION: PositionScaling.NONE,
        }[self.input_basis]
        if self.position_scaling is not expected_scaling:
            raise ValueError(f"{self.input_basis.value} requires {expected_scaling.value} scaling")

    def _validate_output_measure(self) -> None:
        if (
            self.input_basis is ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION
            and self.output_measure is not ValuationOutputMeasure.SETTLEMENT_VARIATION
        ):
            raise ValueError("settlement variation input cannot populate market value or notional")
        if (
            self.output_measure is ValuationOutputMeasure.SETTLEMENT_VARIATION
            and self.input_basis is not ValuationInputBasis.SETTLEMENT_VARIATION_WHOLE_POSITION
        ):
            raise ValueError("settlement variation output requires a settlement variation input")

    def _validate_accrued_income_treatment(self) -> None:
        if self.input_basis is ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY:
            if self.accrued_income_treatment is not AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE:
                raise ValueError("dirty percent-of-principal value must include accrued income")
        elif self.accrued_income_treatment is AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE:
            raise ValueError("included accrued income is valid only for a dirty source value")
        if (
            self.accrued_income_treatment is AccruedIncomeTreatment.CALCULATED_EX_COUPON_SEPARATELY
            and self.input_basis is not ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN
        ):
            raise ValueError(
                "calculated ex-coupon accrual requires a clean percent-of-principal input"
            )
        if self.output_measure is not ValuationOutputMeasure.MARKET_VALUE and (
            self.accrued_income_treatment is not AccruedIncomeTreatment.NOT_APPLICABLE
        ):
            raise ValueError("non-market-value outputs cannot include accrued income")


@dataclass(frozen=True, slots=True)
class PositionValuationEvidence:
    """Source and derived-calculation evidence for position-valuation inputs."""

    policy_assignment: FinancialSourceReference
    source_value: FinancialSourceReference
    source_currency: FinancialSourceReference
    reporting_currency: FinancialSourceReference
    signed_quantity: FinancialSourceReference | None = None
    signed_face_amount: FinancialSourceReference | None = None
    principal_factor: FinancialSourceReference | None = None
    signed_current_principal: FinancialSourceReference | None = None
    contract_multiplier: FinancialSourceReference | None = None
    calculated_accrued_income: CalculationLineage | None = None
    supplied_accrued_income: FinancialSourceReference | None = None
    direct_source_to_reporting_fx_rate: FinancialSourceReference | None = None


@dataclass(frozen=True, slots=True)
class PositionValuationInputs:
    """Authoritative facts and evidence required by a position valuation policy."""

    source_value: Decimal
    signed_quantity: Decimal
    source_currency: str
    reporting_currency: str
    evidence: PositionValuationEvidence
    signed_face_amount: Decimal | None = None
    principal_factor: Decimal | None = None
    signed_current_principal: Decimal | None = None
    contract_multiplier: Decimal | None = None
    calculated_accrued_income: Decimal | None = None
    supplied_accrued_income: Decimal | None = None
    direct_source_to_reporting_fx_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.source_currency.strip():
            raise ValueError("source_currency must be nonblank")
        if not self.reporting_currency.strip():
            raise ValueError("reporting_currency must be nonblank")


@dataclass(frozen=True, slots=True)
class PositionValuationResult:
    """Distinct supported measures produced without implicit rounding."""

    source_currency: str
    reporting_currency: str
    source_to_reporting_fx_rate: Decimal
    current_principal: Decimal | None
    clean_value_local: Decimal | None
    clean_value_reporting: Decimal | None
    accrued_income_local: Decimal | None
    accrued_income_reporting: Decimal | None
    total_market_value_local: Decimal | None
    total_market_value_reporting: Decimal | None
    notional_exposure_local: Decimal | None
    notional_exposure_reporting: Decimal | None
    settlement_variation_local: Decimal | None
    settlement_variation_reporting: Decimal | None
    lineage: CalculationLineage


def calculate_position_valuation(
    *,
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
) -> PositionValuationResult:
    """Apply one declared policy without quote, product, or pricing inference."""

    evidence = inputs.evidence
    _validate_source_value(policy, inputs.source_value)
    with localcontext() as context:
        context.prec = POSITION_VALUATION_INTERMEDIATE_PRECISION
        current_principal = _resolve_current_principal(policy, inputs)
        scaled_value = _scale_source_value(policy, inputs, current_principal)
        accrued_income = _resolve_accrued_income(policy, inputs)
        fx_rate = _resolve_fx_rate(policy, inputs)

        clean_value: Decimal | None = None
        total_market_value: Decimal | None = None
        notional_exposure: Decimal | None = None
        settlement_variation: Decimal | None = None

        if policy.output_measure is ValuationOutputMeasure.MARKET_VALUE:
            if policy.input_basis is ValuationInputBasis.PERCENT_OF_PRINCIPAL_DIRTY:
                total_market_value = scaled_value
            elif policy.input_basis is ValuationInputBasis.PERCENT_OF_PRINCIPAL_CLEAN:
                clean_value = scaled_value
                total_market_value = scaled_value + (accrued_income or Decimal(0))
            else:
                total_market_value = scaled_value + (accrued_income or Decimal(0))
        elif policy.output_measure is ValuationOutputMeasure.NOTIONAL_EXPOSURE:
            notional_exposure = scaled_value
        else:
            settlement_variation = scaled_value

        source_currency = _normalize_currency(inputs.source_currency)
        reporting_currency = _normalize_currency(inputs.reporting_currency)
        accrued_income_reporting = _convert(accrued_income, fx_rate)
        clean_value_reporting = _convert(clean_value, fx_rate)
        notional_exposure_reporting = _convert(notional_exposure, fx_rate)
        settlement_variation_reporting = _convert(settlement_variation, fx_rate)
        total_market_value_reporting = _convert(total_market_value, fx_rate)
        output_payload = {
            "accrued_income_local": accrued_income,
            "accrued_income_reporting": accrued_income_reporting,
            "clean_value_local": clean_value,
            "clean_value_reporting": clean_value_reporting,
            "current_principal": current_principal,
            "notional_exposure_local": notional_exposure,
            "notional_exposure_reporting": notional_exposure_reporting,
            "reporting_currency": reporting_currency,
            "settlement_variation_local": settlement_variation,
            "settlement_variation_reporting": settlement_variation_reporting,
            "source_currency": source_currency,
            "source_to_reporting_fx_rate": fx_rate,
            "total_market_value_local": total_market_value,
            "total_market_value_reporting": total_market_value_reporting,
        }
    lineage = build_calculation_lineage(
        algorithm_id=POSITION_VALUATION_ALGORITHM_ID,
        algorithm_version=POSITION_VALUATION_ALGORITHM_VERSION,
        intermediate_precision=POSITION_VALUATION_INTERMEDIATE_PRECISION,
        input_payload=_position_input_payload(policy=policy, inputs=inputs, evidence=evidence),
        output_payload=output_payload,
    )
    return PositionValuationResult(
        source_currency=source_currency,
        reporting_currency=reporting_currency,
        source_to_reporting_fx_rate=fx_rate,
        current_principal=current_principal,
        clean_value_local=clean_value,
        clean_value_reporting=clean_value_reporting,
        accrued_income_local=accrued_income,
        accrued_income_reporting=accrued_income_reporting,
        total_market_value_local=total_market_value,
        total_market_value_reporting=total_market_value_reporting,
        notional_exposure_local=notional_exposure,
        notional_exposure_reporting=notional_exposure_reporting,
        settlement_variation_local=settlement_variation,
        settlement_variation_reporting=settlement_variation_reporting,
        lineage=lineage,
    )


def _position_input_payload(
    *,
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
    evidence: PositionValuationEvidence,
) -> dict[str, object]:
    consumed_inputs: dict[str, object] = {
        "reporting_currency": _sourced_fact_payload(
            _normalize_currency(inputs.reporting_currency),
            evidence.reporting_currency,
            "reporting_currency evidence",
        ),
        "source_currency": _sourced_fact_payload(
            _normalize_currency(inputs.source_currency),
            evidence.source_currency,
            "source_currency evidence",
        ),
        "source_value": _sourced_fact_payload(
            inputs.source_value,
            evidence.source_value,
            "source_value evidence",
        ),
    }
    if policy.position_scaling in {
        PositionScaling.QUANTITY,
        PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER,
    }:
        consumed_inputs["signed_quantity"] = _sourced_fact_payload(
            inputs.signed_quantity,
            evidence.signed_quantity,
            "signed_quantity evidence",
        )
    if policy.principal_basis is PrincipalBasis.FACE_AMOUNT:
        consumed_inputs["signed_face_amount"] = _sourced_fact_payload(
            _required(inputs.signed_face_amount, "signed_face_amount"),
            evidence.signed_face_amount,
            "signed_face_amount evidence",
        )
    elif policy.principal_basis is PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL:
        consumed_inputs["signed_face_amount"] = _sourced_fact_payload(
            _required(inputs.signed_face_amount, "signed_face_amount"),
            evidence.signed_face_amount,
            "signed_face_amount evidence",
        )
        consumed_inputs["principal_factor"] = _sourced_fact_payload(
            _required(inputs.principal_factor, "principal_factor"),
            evidence.principal_factor,
            "principal_factor evidence",
        )
    elif policy.principal_basis is PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL:
        consumed_inputs["signed_current_principal"] = _sourced_fact_payload(
            _required(inputs.signed_current_principal, "signed_current_principal"),
            evidence.signed_current_principal,
            "signed_current_principal evidence",
        )
    if policy.position_scaling is PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER:
        consumed_inputs["contract_multiplier"] = _sourced_fact_payload(
            _required(inputs.contract_multiplier, "contract_multiplier"),
            evidence.contract_multiplier,
            "contract_multiplier evidence",
        )
    if policy.accrued_income_treatment in {
        AccruedIncomeTreatment.CALCULATED_SEPARATELY,
        AccruedIncomeTreatment.CALCULATED_EX_COUPON_SEPARATELY,
    }:
        accrued_lineage = evidence.calculated_accrued_income
        if accrued_lineage is None:
            raise UnsupportedValuationError("calculated_accrued_income lineage is required")
        consumed_inputs["calculated_accrued_income"] = {
            "calculation_lineage": accrued_lineage.lineage_payload(),
            "value": _required(
                inputs.calculated_accrued_income,
                "calculated_accrued_income",
            ),
        }
    elif policy.accrued_income_treatment is AccruedIncomeTreatment.SUPPLIED_SEPARATELY:
        consumed_inputs["supplied_accrued_income"] = _sourced_fact_payload(
            _required(inputs.supplied_accrued_income, "supplied_accrued_income"),
            evidence.supplied_accrued_income,
            "supplied_accrued_income evidence",
        )
    if (
        policy.fx_conversion is FxConversionPolicy.DIRECT_SOURCE_TO_REPORTING
        and _normalize_currency(inputs.source_currency)
        != _normalize_currency(inputs.reporting_currency)
    ):
        consumed_inputs["direct_source_to_reporting_fx_rate"] = _sourced_fact_payload(
            _required(
                inputs.direct_source_to_reporting_fx_rate,
                "direct_source_to_reporting_fx_rate",
            ),
            evidence.direct_source_to_reporting_fx_rate,
            "direct_source_to_reporting_fx_rate evidence",
        )
    return {
        "inputs": consumed_inputs,
        "policy": {
            "accrued_income_treatment": policy.accrued_income_treatment,
            "fx_conversion": policy.fx_conversion,
            "input_basis": policy.input_basis,
            "output_measure": policy.output_measure,
            "policy_id": policy.policy_id.strip(),
            "policy_version": policy.policy_version,
            "position_scaling": policy.position_scaling,
            "principal_basis": policy.principal_basis,
            "quote_denominator": policy.quote_denominator,
        },
        "policy_assignment": evidence.policy_assignment.lineage_payload(),
    }


def _sourced_fact_payload(
    value: object,
    source: FinancialSourceReference | None,
    field_name: str,
) -> dict[str, object]:
    if source is None:
        raise UnsupportedValuationError(f"{field_name} is required")
    return {"source": source.lineage_payload(), "value": value}


def _validate_source_value(policy: PositionValuationPolicy, source_value: Decimal) -> None:
    if not source_value.is_finite():
        raise UnsupportedValuationError("source_value must be finite")
    if policy.input_basis in _PER_UNIT_BASES | _PERCENT_OF_PRINCIPAL_BASES and source_value <= 0:
        raise UnsupportedValuationError(
            f"{policy.input_basis.value} requires a positive source_value"
        )
    if policy.output_measure is ValuationOutputMeasure.NOTIONAL_EXPOSURE and source_value <= 0:
        raise UnsupportedValuationError("notional exposure requires a positive source_value")


def _resolve_current_principal(
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
) -> Decimal | None:
    if policy.position_scaling is not PositionScaling.PRINCIPAL:
        return None
    if policy.principal_basis is PrincipalBasis.FACE_AMOUNT:
        return _required(inputs.signed_face_amount, "signed_face_amount")
    if policy.principal_basis is PrincipalBasis.FACTOR_ADJUSTED_CURRENT_PRINCIPAL:
        signed_face_amount = _required(inputs.signed_face_amount, "signed_face_amount")
        factor = _required(inputs.principal_factor, "principal_factor")
        if factor < 0 or factor > 1:
            raise UnsupportedValuationError("principal_factor must be between zero and one")
        return signed_face_amount * factor
    if policy.principal_basis is PrincipalBasis.SUPPLIED_CURRENT_PRINCIPAL:
        return _required(inputs.signed_current_principal, "signed_current_principal")
    raise UnsupportedValuationError("POSITION_UNITS cannot supply percent-of-principal valuation")


def _scale_source_value(
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
    current_principal: Decimal | None,
) -> Decimal:
    if policy.position_scaling is PositionScaling.NONE:
        return inputs.source_value
    if policy.position_scaling is PositionScaling.QUANTITY:
        return inputs.signed_quantity * inputs.source_value
    if policy.position_scaling is PositionScaling.CONTRACT_COUNT_AND_MULTIPLIER:
        multiplier = _required(inputs.contract_multiplier, "contract_multiplier")
        if multiplier <= 0:
            raise UnsupportedValuationError("contract_multiplier must be positive")
        return inputs.signed_quantity * inputs.source_value * multiplier
    principal = _required(current_principal, "current_principal")
    denominator = _required(policy.quote_denominator, "quote_denominator")
    return principal * inputs.source_value / denominator


def _resolve_accrued_income(
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
) -> Decimal | None:
    treatment = policy.accrued_income_treatment
    if treatment in {
        AccruedIncomeTreatment.NOT_APPLICABLE,
        AccruedIncomeTreatment.NO_PERIODIC_ACCRUAL,
        AccruedIncomeTreatment.INCLUDED_IN_SOURCE_VALUE,
    }:
        return None
    if treatment in {
        AccruedIncomeTreatment.CALCULATED_SEPARATELY,
        AccruedIncomeTreatment.CALCULATED_EX_COUPON_SEPARATELY,
    }:
        return _required(inputs.calculated_accrued_income, "calculated_accrued_income")
    return _required(inputs.supplied_accrued_income, "supplied_accrued_income")


def _resolve_fx_rate(
    policy: PositionValuationPolicy,
    inputs: PositionValuationInputs,
) -> Decimal:
    source_currency = _normalize_currency(inputs.source_currency)
    reporting_currency = _normalize_currency(inputs.reporting_currency)
    if policy.fx_conversion is FxConversionPolicy.ALREADY_IN_REPORTING_CURRENCY:
        if source_currency != reporting_currency:
            raise UnsupportedValuationError(
                "ALREADY_IN_REPORTING_CURRENCY requires matching currencies"
            )
        return Decimal(1)
    if source_currency == reporting_currency:
        return Decimal(1)
    fx_rate = _required(
        inputs.direct_source_to_reporting_fx_rate,
        "direct_source_to_reporting_fx_rate",
    )
    if fx_rate <= 0:
        raise UnsupportedValuationError("direct_source_to_reporting_fx_rate must be positive")
    return fx_rate


def _required(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise UnsupportedValuationError(f"{field_name} is required by the valuation policy")
    if not value.is_finite():
        raise UnsupportedValuationError(f"{field_name} must be finite")
    return value


def _normalize_currency(value: str) -> str:
    return value.strip().upper()


def _convert(value: Decimal | None, fx_rate: Decimal) -> Decimal | None:
    return value * fx_rate if value is not None else None
