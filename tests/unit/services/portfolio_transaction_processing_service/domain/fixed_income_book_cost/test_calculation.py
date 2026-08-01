"""Tests for deterministic fixed-income amortized-cost schedules."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output

from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizationPeriodInput,
    AmortizedCostCalculationError,
    AmortizedCostDirection,
    AmortizedCostMethod,
    AmortizedCostPolicy,
    AmortizedCostReconciliationError,
    AmortizedCostScheduleInput,
    YieldApplicationConvention,
    calculate_amortized_cost_schedule,
)


def _policy(
    *,
    method: AmortizedCostMethod = AmortizedCostMethod.STRAIGHT_LINE,
    convention: YieldApplicationConvention | None = None,
    tolerance: str = "0.0000000001",
) -> AmortizedCostPolicy:
    return AmortizedCostPolicy(
        policy_id="FI_BOOK_COST",
        policy_version=1,
        method=method,
        yield_application_convention=convention,
        include_fees_in_amortized_cost=True,
        residual_tolerance_local=Decimal(tolerance),
    )


def _period(
    start: date,
    end: date,
    *,
    weight: str = "1",
    coupon: str = "0",
    rate: str | None = None,
) -> AmortizationPeriodInput:
    return AmortizationPeriodInput(
        period_start_date=start,
        period_end_date=end,
        year_fraction=Decimal(weight),
        cash_coupon_local=Decimal(coupon),
        supplied_period_rate=Decimal(rate) if rate is not None else None,
    )


def test_straight_line_irregular_periods_conserve_discount_and_replay_identically() -> None:
    inputs = AmortizedCostScheduleInput(
        initial_clean_cost_local=Decimal("92"),
        fees_in_basis_local=Decimal("0"),
        redemption_value_local=Decimal("100"),
        periods=(
            _period(date(2026, 1, 1), date(2026, 4, 1), weight="0.25"),
            _period(date(2026, 4, 1), date(2027, 1, 1), weight="0.75"),
        ),
    )

    first = calculate_amortized_cost_schedule(policy=_policy(), inputs=inputs)
    replay = calculate_amortized_cost_schedule(policy=_policy(), inputs=inputs)

    assert first.direction is AmortizedCostDirection.DISCOUNT_ACCRETION
    assert [row.amortization_amount_local for row in first.periods] == [
        Decimal("2.0000000000"),
        Decimal("6.0000000000"),
    ]
    assert first.final_amortized_cost_local == Decimal("100.0000000000")
    assert first.residual_local == Decimal("0E-10")
    assert first == replay


def test_effective_yield_premium_schedule_reconciles_and_binds_lineage() -> None:
    inputs = AmortizedCostScheduleInput(
        initial_clean_cost_local=Decimal("105"),
        fees_in_basis_local=Decimal("0"),
        redemption_value_local=Decimal("100"),
        periods=(
            _period(
                date(2026, 1, 1),
                date(2027, 1, 1),
                coupon="8.15",
            ),
        ),
        annual_yield=Decimal("0.03"),
    )
    result = calculate_amortized_cost_schedule(
        policy=_policy(
            method=AmortizedCostMethod.EFFECTIVE_YIELD,
            convention=YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
        ),
        inputs=inputs,
    )

    assert result.direction is AmortizedCostDirection.PREMIUM_AMORTIZATION
    assert result.periods[0].interest_income_local == Decimal("3.1500000000")
    assert result.periods[0].amortization_amount_local == Decimal("-5.0000000000")
    assert result.final_amortized_cost_local == Decimal("100.0000000000")
    assert result.lineage.numeric_output_policy is not None
    assert result.lineage.numeric_output_policy.policy_id == (
        "cost-basis-state-ledger-output@1.0.0"
    )
    assert calculation_lineage_binds_output(
        result.lineage,
        output_payload={
            "direction": result.direction.value,
            "final_amortized_cost_local": result.final_amortized_cost_local,
            "initial_amortized_cost_local": result.initial_amortized_cost_local,
            "periods": [
                {
                    "amortization_amount_local": row.amortization_amount_local,
                    "begin_amortized_cost_local": row.begin_amortized_cost_local,
                    "cash_coupon_local": row.cash_coupon_local,
                    "end_amortized_cost_local": row.end_amortized_cost_local,
                    "interest_income_local": row.interest_income_local,
                    "period_end_date": row.period_end_date,
                    "period_rate": row.period_rate,
                    "period_start_date": row.period_start_date,
                    "rounding_adjustment_local": row.rounding_adjustment_local,
                    "year_fraction": row.year_fraction,
                }
                for row in result.periods
            ],
            "redemption_value_local": result.redemption_value_local,
            "residual_local": result.residual_local,
        },
    )


@pytest.mark.parametrize(
    ("convention", "annual_yield", "period_rate", "initial", "redemption"),
    [
        (
            YieldApplicationConvention.ANNUAL_EFFECTIVE,
            Decimal("0.21"),
            None,
            Decimal("100"),
            Decimal("110"),
        ),
        (
            YieldApplicationConvention.ANNUAL_NOMINAL_SIMPLE,
            Decimal("0.20"),
            None,
            Decimal("100"),
            Decimal("110"),
        ),
        (
            YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
            None,
            Decimal("0.10"),
            Decimal("100"),
            Decimal("110"),
        ),
    ],
)
def test_effective_yield_conventions_apply_governed_period_rate(
    convention: YieldApplicationConvention,
    annual_yield: Decimal | None,
    period_rate: Decimal | None,
    initial: Decimal,
    redemption: Decimal,
) -> None:
    result = calculate_amortized_cost_schedule(
        policy=_policy(
            method=AmortizedCostMethod.EFFECTIVE_YIELD,
            convention=convention,
        ),
        inputs=AmortizedCostScheduleInput(
            initial_clean_cost_local=initial,
            fees_in_basis_local=Decimal("0"),
            redemption_value_local=redemption,
            periods=(
                _period(
                    date(2026, 1, 1),
                    date(2026, 7, 1),
                    weight="0.5",
                    rate=str(period_rate) if period_rate is not None else None,
                ),
            ),
            annual_yield=annual_yield,
        ),
    )

    assert result.periods[0].period_rate == Decimal("0.10")
    assert result.periods[0].interest_income_local == Decimal("10.0000000000")
    assert result.final_amortized_cost_local == Decimal("110.0000000000")


def test_negative_effective_yield_is_supported_when_economics_reconcile() -> None:
    result = calculate_amortized_cost_schedule(
        policy=_policy(
            method=AmortizedCostMethod.EFFECTIVE_YIELD,
            convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
        ),
        inputs=AmortizedCostScheduleInput(
            initial_clean_cost_local=Decimal("100"),
            fees_in_basis_local=Decimal("0"),
            redemption_value_local=Decimal("99"),
            periods=(
                _period(
                    date(2026, 1, 1),
                    date(2027, 1, 1),
                    rate="-0.01",
                ),
            ),
        ),
    )

    assert result.direction is AmortizedCostDirection.PREMIUM_AMORTIZATION
    assert result.periods[0].interest_income_local == Decimal("-1.0000000000")
    assert result.final_amortized_cost_local == Decimal("99.0000000000")


def test_effective_yield_row_explains_sub_quantum_rounding() -> None:
    result = calculate_amortized_cost_schedule(
        policy=_policy(
            method=AmortizedCostMethod.EFFECTIVE_YIELD,
            convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
        ),
        inputs=AmortizedCostScheduleInput(
            initial_clean_cost_local=Decimal("1"),
            fees_in_basis_local=Decimal("0"),
            redemption_value_local=Decimal("1"),
            periods=(
                _period(
                    date(2026, 1, 1),
                    date(2027, 1, 1),
                    coupon="0.00000000004",
                    rate="0.00000000006",
                ),
            ),
        ),
    )

    row = result.periods[0]
    assert row.interest_income_local == Decimal("0.0000000001")
    assert row.cash_coupon_local == Decimal("0E-10")
    assert row.amortization_amount_local == Decimal("0E-10")
    assert row.rounding_adjustment_local == Decimal("-0.0000000001")
    assert row.amortization_amount_local == (
        row.interest_income_local - row.cash_coupon_local + row.rounding_adjustment_local
    )


def test_equal_outputs_from_distinct_economic_inputs_have_distinct_lineage() -> None:
    periods = (_period(date(2026, 1, 1), date(2027, 1, 1)),)
    first = calculate_amortized_cost_schedule(
        policy=_policy(),
        inputs=AmortizedCostScheduleInput(
            initial_clean_cost_local=Decimal("92"),
            fees_in_basis_local=Decimal("0"),
            redemption_value_local=Decimal("100"),
            periods=periods,
        ),
    )
    second = calculate_amortized_cost_schedule(
        policy=replace(_policy(), include_fees_in_amortized_cost=False),
        inputs=AmortizedCostScheduleInput(
            initial_clean_cost_local=Decimal("92"),
            fees_in_basis_local=Decimal("8"),
            redemption_value_local=Decimal("100"),
            periods=periods,
        ),
    )

    assert first.final_amortized_cost_local == second.final_amortized_cost_local
    assert first.lineage.input_content_hash != second.lineage.input_content_hash
    assert first.lineage.calculation_content_hash != second.lineage.calculation_content_hash


@pytest.mark.parametrize(
    ("policy", "inputs", "message"),
    [
        (
            _policy(
                method=AmortizedCostMethod.EFFECTIVE_YIELD,
                convention=YieldApplicationConvention.ANNUAL_EFFECTIVE,
            ),
            AmortizedCostScheduleInput(
                initial_clean_cost_local=Decimal("92"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                periods=(_period(date(2026, 1, 1), date(2027, 1, 1)),),
            ),
            "require annual_yield",
        ),
        (
            _policy(
                method=AmortizedCostMethod.EFFECTIVE_YIELD,
                convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
            ),
            AmortizedCostScheduleInput(
                initial_clean_cost_local=Decimal("92"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                periods=(_period(date(2026, 1, 1), date(2027, 1, 1)),),
            ),
            "requires supplied_period_rate",
        ),
        (
            _policy(),
            AmortizedCostScheduleInput(
                initial_clean_cost_local=Decimal("92"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                periods=(_period(date(2026, 1, 1), date(2027, 1, 1)),),
                annual_yield=Decimal("0.03"),
            ),
            "must not declare yield inputs",
        ),
    ],
)
def test_ambiguous_or_missing_rate_authority_fails_closed(
    policy: AmortizedCostPolicy,
    inputs: AmortizedCostScheduleInput,
    message: str,
) -> None:
    with pytest.raises(AmortizedCostCalculationError, match=message):
        calculate_amortized_cost_schedule(policy=policy, inputs=inputs)


def test_nonreconciling_effective_yield_fails_closed() -> None:
    with pytest.raises(AmortizedCostReconciliationError, match="within tolerance"):
        calculate_amortized_cost_schedule(
            policy=_policy(
                method=AmortizedCostMethod.EFFECTIVE_YIELD,
                convention=YieldApplicationConvention.PER_PERIOD_EFFECTIVE,
                tolerance="0.01",
            ),
            inputs=AmortizedCostScheduleInput(
                initial_clean_cost_local=Decimal("92"),
                fees_in_basis_local=Decimal("0"),
                redemption_value_local=Decimal("100"),
                periods=(
                    _period(
                        date(2026, 1, 1),
                        date(2027, 1, 1),
                        rate="0.01",
                    ),
                ),
            ),
        )


def test_schedule_rejects_gaps_and_invalid_period_economics() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        AmortizedCostScheduleInput(
            initial_clean_cost_local=Decimal("92"),
            fees_in_basis_local=Decimal("0"),
            redemption_value_local=Decimal("100"),
            periods=(
                _period(date(2026, 1, 1), date(2026, 4, 1)),
                _period(date(2026, 4, 2), date(2027, 1, 1)),
            ),
        )
    with pytest.raises(ValueError, match="cash_coupon_local must be nonnegative"):
        _period(date(2026, 1, 1), date(2027, 1, 1), coupon="-1")
