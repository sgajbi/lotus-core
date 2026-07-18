"""Golden tests for segmented gross contractual accrued income."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest
from portfolio_common.domain.valuation import (
    AccrualRateType,
    AccrualSegment,
    AccrualSourceReference,
    IcmaReferencePeriod,
    UnsupportedAccruedIncomeError,
    UnsupportedDayCountError,
    calculate_segmented_accrued_income,
    canonical_content_hash,
)


def _source(fact: str) -> AccrualSourceReference:
    return AccrualSourceReference(
        source_system="security_master",
        source_record_id=f"BOND-001:{fact}",
        source_revision="revision-9",
        source_content_hash=canonical_content_hash({"fact": fact, "revision": 9}),
        observed_at=datetime(2026, 1, 2, 8, tzinfo=UTC),
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return Decimal(numerator) / Decimal(denominator)


def _accrual(principal: str, rate: str, days: int, denominator: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return Decimal(principal) * Decimal(rate) * _ratio(days, denominator)


def _sum_accruals(*values: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return sum(values, start=Decimal(0))


def _segment(**overrides: object) -> AccrualSegment:
    values: dict[str, object] = {
        "accrual_start": date(2026, 1, 1),
        "accrual_end": date(2026, 7, 1),
        "currency": "USD",
        "signed_accrual_principal": Decimal("1000000"),
        "annual_effective_rate": Decimal("0.06"),
        "rate_type": AccrualRateType.FIXED,
        "day_count_convention": "ACT/ACT.ICMA",
        "day_count_convention_version": 1,
        "rate_source": _source("rate"),
        "principal_source": _source("principal"),
        "schedule_source": _source("schedule"),
        "icma_reference_periods": (IcmaReferencePeriod(date(2026, 1, 1), date(2026, 7, 1), 2),),
    }
    values.update(overrides)
    return AccrualSegment(**values)  # type: ignore[arg-type]


def test_fixed_rate_regular_coupon_uses_governed_year_fraction() -> None:
    result = calculate_segmented_accrued_income((_segment(),))

    assert result.currency == "USD"
    assert result.gross_accrued_income == Decimal("30000.000")
    assert result.segments[0].year_fraction == Decimal("0.5")


def test_supplied_floating_all_in_rate_is_not_derived_or_divided_by_frequency() -> None:
    segment = _segment(
        accrual_end=date(2026, 4, 2),
        annual_effective_rate=Decimal("0.0525"),
        rate_type=AccrualRateType.FLOATING_SUPPLIED,
        day_count_convention="ACT/360",
        icma_reference_periods=(),
    )

    result = calculate_segmented_accrued_income((segment,))

    assert result.segments[0].year_fraction == _ratio(91, 360)
    assert result.gross_accrued_income == _accrual("1000000", "0.0525", 91, 360)


def test_principal_change_segments_accrue_on_each_authoritative_balance() -> None:
    first = _segment(
        accrual_end=date(2026, 4, 1),
        day_count_convention="ACT/365.FIXED",
        icma_reference_periods=(),
    )
    second = replace(
        first,
        accrual_start=date(2026, 4, 1),
        accrual_end=date(2026, 7, 1),
        signed_accrual_principal=Decimal("800000"),
        principal_source=_source("principal-paydown-1"),
    )

    result = calculate_segmented_accrued_income((second, first))

    assert [item.signed_accrual_principal for item in result.segments] == [
        Decimal("1000000"),
        Decimal("800000"),
    ]
    assert result.gross_accrued_income == _sum_accruals(
        _accrual("1000000", "0.06", 90, 365),
        _accrual("800000", "0.06", 91, 365),
    )
    assert len(result.lineage.input_content_hash) == 64
    assert len(result.lineage.calculation_content_hash) == 64
    assert len(result.lineage.output_content_hash) == 64


def test_rate_reset_segments_use_each_supplied_all_in_rate() -> None:
    first = _segment(
        accrual_end=date(2026, 4, 1),
        rate_type=AccrualRateType.FLOATING_SUPPLIED,
        annual_effective_rate=Decimal("0.041"),
        day_count_convention="ACT/360",
        icma_reference_periods=(),
    )
    second = replace(
        first,
        accrual_start=date(2026, 4, 1),
        accrual_end=date(2026, 7, 1),
        annual_effective_rate=Decimal("0.0475"),
        rate_source=_source("rate-reset-2"),
    )

    result = calculate_segmented_accrued_income((first, second))

    assert result.gross_accrued_income == _sum_accruals(
        _accrual("1000000", "0.041", 90, 360),
        _accrual("1000000", "0.0475", 91, 360),
    )


def test_calculation_is_independent_of_ambient_decimal_precision() -> None:
    segment = _segment(day_count_convention="ACT/365.FIXED", icma_reference_periods=())
    expected = calculate_segmented_accrued_income((segment,))

    with localcontext() as context:
        context.prec = 9
        actual = calculate_segmented_accrued_income((segment,))

    assert actual == expected


def test_lineage_is_input_order_independent_but_source_revision_sensitive() -> None:
    first = _segment(
        accrual_end=date(2026, 4, 1),
        day_count_convention="ACT/360",
        icma_reference_periods=(),
    )
    second = replace(first, accrual_start=date(2026, 4, 1), accrual_end=date(2026, 7, 1))

    ordered = calculate_segmented_accrued_income((first, second))
    reversed_input = calculate_segmented_accrued_income((second, first))
    revised_source = calculate_segmented_accrued_income(
        (first, replace(second, rate_source=_source("rate-revision-10")))
    )

    assert reversed_input.lineage == ordered.lineage
    assert revised_source.gross_accrued_income == ordered.gross_accrued_income
    assert revised_source.lineage.input_content_hash != ordered.lineage.input_content_hash
    assert (
        revised_source.lineage.calculation_content_hash != ordered.lineage.calculation_content_hash
    )
    assert revised_source.lineage.output_content_hash != ordered.lineage.output_content_hash


@pytest.mark.parametrize(
    ("principal", "rate", "expected_sign"),
    [
        (Decimal("-1000000"), Decimal("0.06"), -1),
        (Decimal("1000000"), Decimal("-0.0025"), -1),
        (Decimal("-1000000"), Decimal("-0.0025"), 1),
        (Decimal("1000000"), Decimal("0"), 0),
    ],
)
def test_signed_principal_and_contractual_zero_or_negative_rates_are_preserved(
    principal: Decimal,
    rate: Decimal,
    expected_sign: int,
) -> None:
    result = calculate_segmented_accrued_income(
        (_segment(signed_accrual_principal=principal, annual_effective_rate=rate),)
    )

    assert result.gross_accrued_income.compare(Decimal(0)) == Decimal(expected_sign)


@pytest.mark.parametrize(
    ("second_start", "message"),
    [
        (date(2026, 3, 31), "overlap"),
        (date(2026, 4, 2), "gap"),
    ],
)
def test_segment_overlap_or_gap_fails_closed(second_start: date, message: str) -> None:
    first = _segment(
        accrual_end=date(2026, 4, 1),
        day_count_convention="ACT/360",
        icma_reference_periods=(),
    )
    second = replace(
        first,
        accrual_start=second_start,
        accrual_end=date(2026, 7, 1),
    )

    with pytest.raises(UnsupportedAccruedIncomeError, match=message):
        calculate_segmented_accrued_income((first, second))


def test_empty_or_mixed_currency_segments_fail_closed() -> None:
    with pytest.raises(UnsupportedAccruedIncomeError, match="at least one"):
        calculate_segmented_accrued_income(())
    with pytest.raises(UnsupportedAccruedIncomeError, match="one currency"):
        calculate_segmented_accrued_income(
            (
                _segment(accrual_end=date(2026, 4, 1)),
                _segment(
                    accrual_start=date(2026, 4, 1),
                    currency="EUR",
                ),
            )
        )


def test_missing_day_count_support_and_invalid_source_facts_fail_closed() -> None:
    with pytest.raises(UnsupportedDayCountError, match="unsupported day-count"):
        calculate_segmented_accrued_income((_segment(day_count_convention="ACT/365.UNKNOWN"),))
    with pytest.raises(ValueError, match="finite"):
        _segment(annual_effective_rate=Decimal("NaN"))
    with pytest.raises(ValueError, match="source_revision"):
        AccrualSourceReference(
            "security_master",
            "BOND-001:rate",
            " ",
            "a" * 64,
            datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_source("rate"), observed_at=datetime(2026, 1, 1))
