"""Application mapping from authoritative facts to the valuation domain kernel."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.valuation import (
    MarketPriceSourceFact,
    PositionValuationEvidence,
    PositionValuationInputs,
    PositionValuationPolicy,
    UnsupportedValuationError,
    ValuationOutputMeasure,
    calculate_position_valuation,
    validate_market_price_policy_compatibility,
)
from portfolio_common.domain.valuation.numeric_policy import (
    POSITION_VALUATION_LEDGER_OUTPUT_V1,
)


@dataclass(frozen=True, slots=True)
class AuthoritativeValuationRequest:
    """All facts required to execute one explicitly assigned market-value policy."""

    policy: PositionValuationPolicy
    price_fact: MarketPriceSourceFact
    signed_quantity: Decimal
    cost_basis_reporting: Decimal
    cost_basis_local: Decimal
    reporting_currency: str
    evidence: PositionValuationEvidence
    direct_source_to_reporting_fx_rate: Decimal | None = None
    signed_face_amount: Decimal | None = None
    principal_factor: Decimal | None = None
    signed_current_principal: Decimal | None = None
    calculated_accrued_income: Decimal | None = None
    supplied_accrued_income: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AuthoritativeValuationResult:
    """Ledger outputs and deterministic calculation lineage for persistence."""

    market_value_reporting: Decimal
    market_value_local: Decimal
    unrealized_total_reporting: Decimal
    unrealized_total_local: Decimal
    unrealized_price_reporting: Decimal
    unrealized_fx_reporting: Decimal
    calculation_lineage: CalculationLineage


def calculate_authoritative_valuation(
    request: AuthoritativeValuationRequest,
) -> AuthoritativeValuationResult:
    """Execute a source-compatible policy and preserve the legacy P&L decomposition."""

    validate_market_price_policy_compatibility(
        fact=request.price_fact,
        policy=request.policy,
    )
    if request.policy.output_measure is not ValuationOutputMeasure.MARKET_VALUE:
        raise UnsupportedValuationError(
            "position snapshot publication requires a MARKET_VALUE policy"
        )

    result = calculate_position_valuation(
        policy=request.policy,
        inputs=PositionValuationInputs(
            source_value=request.price_fact.price,
            signed_quantity=request.signed_quantity,
            source_currency=request.price_fact.currency,
            reporting_currency=request.reporting_currency,
            evidence=request.evidence,
            signed_face_amount=request.signed_face_amount,
            principal_factor=request.principal_factor,
            signed_current_principal=request.signed_current_principal,
            calculated_accrued_income=request.calculated_accrued_income,
            supplied_accrued_income=request.supplied_accrued_income,
            direct_source_to_reporting_fx_rate=request.direct_source_to_reporting_fx_rate,
        ),
    )
    market_value_local = _required_market_value(
        result.total_market_value_local,
        "total_market_value_local",
    )
    market_value_reporting = _required_market_value(
        result.total_market_value_reporting,
        "total_market_value_reporting",
    )
    output_policy = POSITION_VALUATION_LEDGER_OUTPUT_V1
    unrealized_total_local = output_policy.subtract(
        market_value_local,
        request.cost_basis_local,
        field_name="unrealized_gain_loss_local",
    )
    unrealized_total_reporting = output_policy.subtract(
        market_value_reporting,
        request.cost_basis_reporting,
        field_name="unrealized_gain_loss",
    )
    unrealized_fx_reporting = output_policy.subtract(
        output_policy.multiply(
            request.cost_basis_local,
            result.source_to_reporting_fx_rate,
            field_name="current_cost_basis_reporting",
        ),
        request.cost_basis_reporting,
        field_name="unrealized_fx_gain_loss",
    )
    unrealized_price_reporting = output_policy.subtract(
        unrealized_total_reporting,
        unrealized_fx_reporting,
        field_name="unrealized_price_gain_loss",
    )
    calculation_lineage = build_calculation_lineage(
        algorithm_id="authoritative-position-snapshot-valuation",
        algorithm_version=1,
        intermediate_precision=output_policy.working_precision,
        input_payload={
            "cost_basis_local": request.cost_basis_local,
            "cost_basis_reporting": request.cost_basis_reporting,
            "position_valuation": result.lineage.lineage_payload(),
        },
        output_payload={
            "market_value_local": market_value_local,
            "market_value_reporting": market_value_reporting,
            "unrealized_fx_reporting": unrealized_fx_reporting,
            "unrealized_price_reporting": unrealized_price_reporting,
            "unrealized_total_local": unrealized_total_local,
            "unrealized_total_reporting": unrealized_total_reporting,
        },
        numeric_output_policy=output_policy.lineage_identity(),
    )
    return AuthoritativeValuationResult(
        market_value_reporting=market_value_reporting,
        market_value_local=market_value_local,
        unrealized_total_reporting=unrealized_total_reporting,
        unrealized_total_local=unrealized_total_local,
        unrealized_price_reporting=unrealized_price_reporting,
        unrealized_fx_reporting=unrealized_fx_reporting,
        calculation_lineage=calculation_lineage,
    )


def _required_market_value(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise UnsupportedValuationError(f"{field_name} was not produced by the valuation policy")
    return value
