"""Deterministic amortized-cost schedule calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)

from .policy import (
    AmortizedCostDirection,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    YieldApplicationConvention,
    classify_amortized_cost_direction,
)

AMORTIZED_COST_SCHEDULE_ALGORITHM_ID = "fixed-income-amortized-cost-schedule"
AMORTIZED_COST_SCHEDULE_ALGORITHM_VERSION = 1


class AmortizedCostCalculationError(ValueError):
    """Raised when authoritative schedule inputs cannot produce a valid schedule."""


class AmortizedCostReconciliationError(AmortizedCostCalculationError):
    """Raised when effective-yield outputs do not reconcile to redemption value."""


@dataclass(frozen=True, slots=True)
class AmortizationPeriodInput:
    """Authoritative inputs for one contractual amortization period."""

    period_start_date: date
    period_end_date: date
    year_fraction: Decimal
    cash_coupon_local: Decimal
    supplied_period_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.period_start_date) is not date:
            raise TypeError("period_start_date must be a date")
        if type(self.period_end_date) is not date:
            raise TypeError("period_end_date must be a date")
        if self.period_end_date <= self.period_start_date:
            raise ValueError("period_end_date must be after period_start_date")
        _require_finite(self.year_fraction, "year_fraction")
        if self.year_fraction <= 0:
            raise ValueError("year_fraction must be positive")
        _require_nonnegative(self.cash_coupon_local, "cash_coupon_local")
        if self.supplied_period_rate is not None:
            _require_valid_rate(self.supplied_period_rate, "supplied_period_rate")


@dataclass(frozen=True, slots=True)
class AmortizedCostScheduleInput:
    """Complete authoritative inputs for one lot schedule version."""

    initial_clean_cost_local: Decimal
    fees_in_basis_local: Decimal
    redemption_value_local: Decimal
    periods: tuple[AmortizationPeriodInput, ...]
    annual_yield: Decimal | None = None

    def __post_init__(self) -> None:
        _require_nonnegative(self.initial_clean_cost_local, "initial_clean_cost_local")
        _require_nonnegative(self.fees_in_basis_local, "fees_in_basis_local")
        _require_nonnegative(self.redemption_value_local, "redemption_value_local")
        if not isinstance(self.periods, tuple):
            raise TypeError("periods must be a tuple")
        if not self.periods:
            raise ValueError("periods must not be empty")
        for index, period in enumerate(self.periods):
            if not isinstance(period, AmortizationPeriodInput):
                raise TypeError("periods must contain AmortizationPeriodInput values")
            if index and self.periods[index - 1].period_end_date != period.period_start_date:
                raise ValueError("periods must be contiguous and ordered")
        if self.annual_yield is not None:
            _require_valid_rate(self.annual_yield, "annual_yield")


@dataclass(frozen=True, slots=True)
class AmortizationPeriodResult:
    """Normalized amortized-cost result for one contractual period."""

    period_start_date: date
    period_end_date: date
    year_fraction: Decimal
    period_rate: Decimal | None
    begin_amortized_cost_local: Decimal
    interest_income_local: Decimal
    cash_coupon_local: Decimal
    amortization_amount_local: Decimal
    end_amortized_cost_local: Decimal
    rounding_adjustment_local: Decimal


@dataclass(frozen=True, slots=True)
class AmortizedCostScheduleResult:
    """Reconciled schedule plus deterministic calculation lineage."""

    direction: AmortizedCostDirection
    initial_amortized_cost_local: Decimal
    redemption_value_local: Decimal
    final_amortized_cost_local: Decimal
    residual_local: Decimal
    periods: tuple[AmortizationPeriodResult, ...]
    lineage: CalculationLineage


def calculate_amortized_cost_schedule(
    *,
    policy: AmortizedCostPolicy,
    inputs: AmortizedCostScheduleInput,
) -> AmortizedCostScheduleResult:
    """Calculate one deterministic, reconciliation-fenced lot schedule."""

    if not isinstance(policy, AmortizedCostPolicy):
        raise TypeError("policy must be an AmortizedCostPolicy")
    if not isinstance(inputs, AmortizedCostScheduleInput):
        raise TypeError("inputs must be an AmortizedCostScheduleInput")
    _validate_rate_authority(policy, inputs)
    numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    fee_basis = inputs.fees_in_basis_local if policy.include_fees_in_amortized_cost else Decimal(0)
    with numeric_policy.arithmetic_context():
        initial = numeric_policy.add(
            inputs.initial_clean_cost_local,
            fee_basis,
            field_name="initial_amortized_cost_local",
        )
        redemption = numeric_policy.normalize(
            inputs.redemption_value_local,
            field_name="redemption_value_local",
        )
        direction = classify_amortized_cost_direction(
            opening_amortized_cost_local=initial,
            redemption_value_local=redemption,
        )
        remaining_weight = sum((period.year_fraction for period in inputs.periods), Decimal(0))
        begin = initial
        rows: list[AmortizationPeriodResult] = []
        for index, period in enumerate(inputs.periods):
            is_final = index == len(inputs.periods) - 1
            row = _calculate_period(
                policy=policy,
                period=period,
                begin=begin,
                redemption_value=redemption,
                annual_yield=inputs.annual_yield,
                remaining_weight=remaining_weight,
                is_final=is_final,
            )
            rows.append(row)
            begin = row.end_amortized_cost_local
            remaining_weight -= period.year_fraction

    residual = numeric_policy.subtract(
        redemption,
        begin,
        field_name="residual_local",
    )
    if abs(residual) > policy.residual_tolerance_local:
        raise AmortizedCostReconciliationError(
            "final amortized cost does not reconcile to redemption value within tolerance"
        )
    output_payload = amortized_cost_schedule_output_payload(
        direction=direction,
        initial=initial,
        redemption=redemption,
        final=begin,
        residual=residual,
        periods=tuple(rows),
    )
    lineage = build_calculation_lineage(
        algorithm_id=AMORTIZED_COST_SCHEDULE_ALGORITHM_ID,
        algorithm_version=AMORTIZED_COST_SCHEDULE_ALGORITHM_VERSION,
        intermediate_precision=numeric_policy.working_precision,
        input_payload=_input_payload(policy, inputs),
        output_payload=output_payload,
        numeric_output_policy=numeric_policy.lineage_identity(),
    )
    return AmortizedCostScheduleResult(
        direction=direction,
        initial_amortized_cost_local=initial,
        redemption_value_local=redemption,
        final_amortized_cost_local=begin,
        residual_local=residual,
        periods=tuple(rows),
        lineage=lineage,
    )


def _calculate_period(
    *,
    policy: AmortizedCostPolicy,
    period: AmortizationPeriodInput,
    begin: Decimal,
    redemption_value: Decimal,
    annual_yield: Decimal | None,
    remaining_weight: Decimal,
    is_final: bool,
) -> AmortizationPeriodResult:
    numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    period_rate: Decimal | None
    if policy.method is AmortizedCostMethod.STRAIGHT_LINE:
        period_rate = None
        raw_movement = (
            (redemption_value - begin)
            if is_final
            else ((redemption_value - begin) * period.year_fraction / remaining_weight)
        )
        interest = period.cash_coupon_local + raw_movement
    else:
        period_rate = _resolve_period_rate(policy, period, annual_yield)
        interest = begin * period_rate
        raw_movement = interest - period.cash_coupon_local
    movement = numeric_policy.normalize(raw_movement, field_name="amortization_amount_local")
    normalized_interest = numeric_policy.normalize(interest, field_name="interest_income_local")
    normalized_coupon = numeric_policy.normalize(
        period.cash_coupon_local,
        field_name="cash_coupon_local",
    )
    end = numeric_policy.add(begin, movement, field_name="end_amortized_cost_local")
    if end < 0:
        raise AmortizedCostCalculationError("end amortized cost must be nonnegative")
    rounding_adjustment = numeric_policy.normalize(
        movement - (normalized_interest - normalized_coupon),
        field_name="rounding_adjustment_local",
    )
    return AmortizationPeriodResult(
        period_start_date=period.period_start_date,
        period_end_date=period.period_end_date,
        year_fraction=period.year_fraction,
        period_rate=period_rate,
        begin_amortized_cost_local=begin,
        interest_income_local=normalized_interest,
        cash_coupon_local=normalized_coupon,
        amortization_amount_local=movement,
        end_amortized_cost_local=end,
        rounding_adjustment_local=rounding_adjustment,
    )


def _validate_rate_authority(
    policy: AmortizedCostPolicy,
    inputs: AmortizedCostScheduleInput,
) -> None:
    convention = policy.yield_application_convention
    if policy.method is AmortizedCostMethod.STRAIGHT_LINE:
        if inputs.annual_yield is not None or any(
            period.supplied_period_rate is not None for period in inputs.periods
        ):
            raise AmortizedCostCalculationError(
                "straight-line schedules must not declare yield inputs"
            )
        return
    if convention is YieldApplicationConvention.PER_PERIOD_EFFECTIVE:
        if inputs.annual_yield is not None:
            raise AmortizedCostCalculationError(
                "per-period-effective schedules must not declare annual_yield"
            )
        if any(period.supplied_period_rate is None for period in inputs.periods):
            raise AmortizedCostCalculationError(
                "each per-period-effective period requires supplied_period_rate"
            )
        return
    if inputs.annual_yield is None:
        raise AmortizedCostCalculationError("annual-yield schedules require annual_yield")
    if any(period.supplied_period_rate is not None for period in inputs.periods):
        raise AmortizedCostCalculationError(
            "annual-yield schedules must not declare supplied_period_rate"
        )


def _resolve_period_rate(
    policy: AmortizedCostPolicy,
    period: AmortizationPeriodInput,
    annual_yield: Decimal | None,
) -> Decimal:
    convention = policy.yield_application_convention
    if convention is YieldApplicationConvention.PER_PERIOD_EFFECTIVE:
        if period.supplied_period_rate is None:
            raise AmortizedCostCalculationError(
                "per-period-effective period requires supplied_period_rate"
            )
        return period.supplied_period_rate
    if annual_yield is None:
        raise AmortizedCostCalculationError("annual-yield period requires annual_yield")
    if convention is YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE:
        return annual_yield * period.year_fraction
    if convention is YieldApplicationConvention.ANNUAL_EFFECTIVE:
        if annual_yield <= Decimal(-1):
            raise AmortizedCostCalculationError(
                "annual effective yield must be greater than negative one"
            )
        try:
            return (Decimal(1) + annual_yield) ** period.year_fraction - Decimal(1)
        except DecimalException as exc:
            raise AmortizedCostCalculationError(
                "annual effective yield cannot be applied to the governed year fraction"
            ) from exc
    raise AmortizedCostCalculationError("unsupported yield application convention")


def _input_payload(
    policy: AmortizedCostPolicy,
    inputs: AmortizedCostScheduleInput,
) -> dict[str, object]:
    return {
        "annual_yield": inputs.annual_yield,
        "fees_in_basis_local": inputs.fees_in_basis_local,
        "initial_clean_cost_local": inputs.initial_clean_cost_local,
        "periods": [
            {
                "cash_coupon_local": period.cash_coupon_local,
                "period_end_date": period.period_end_date,
                "period_start_date": period.period_start_date,
                "supplied_period_rate": period.supplied_period_rate,
                "year_fraction": period.year_fraction,
            }
            for period in inputs.periods
        ],
        "policy": {
            "include_fees_in_amortized_cost": policy.include_fees_in_amortized_cost,
            "method": policy.method.value,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "residual_tolerance_local": policy.residual_tolerance_local,
            "yield_application_convention": (
                policy.yield_application_convention.value
                if policy.yield_application_convention is not None
                else None
            ),
        },
        "redemption_value_local": inputs.redemption_value_local,
    }


def amortized_cost_schedule_output_payload(
    *,
    direction: AmortizedCostDirection,
    initial: Decimal,
    redemption: Decimal,
    final: Decimal,
    residual: Decimal,
    periods: tuple[AmortizationPeriodResult, ...],
) -> dict[str, object]:
    """Return the canonical normalized schedule output bound by calculation lineage."""

    return {
        "direction": direction.value,
        "final_amortized_cost_local": final,
        "initial_amortized_cost_local": initial,
        "periods": [
            {
                "amortization_amount_local": period.amortization_amount_local,
                "begin_amortized_cost_local": period.begin_amortized_cost_local,
                "cash_coupon_local": period.cash_coupon_local,
                "end_amortized_cost_local": period.end_amortized_cost_local,
                "interest_income_local": period.interest_income_local,
                "period_end_date": period.period_end_date,
                "period_rate": period.period_rate,
                "period_start_date": period.period_start_date,
                "rounding_adjustment_local": period.rounding_adjustment_local,
                "year_fraction": period.year_fraction,
            }
            for period in periods
        ],
        "redemption_value_local": redemption,
        "residual_local": residual,
    }


def _require_finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _require_nonnegative(value: Decimal, field_name: str) -> None:
    _require_finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")


def _require_valid_rate(value: Decimal, field_name: str) -> None:
    _require_finite(value, field_name)
    if value <= Decimal(-1):
        raise ValueError(f"{field_name} must be greater than negative one")
