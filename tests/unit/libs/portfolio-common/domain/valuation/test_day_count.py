"""Golden tests for exact fixed-denominator and business-day conventions."""

from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    BusinessDayCalendar,
    DayCountInputs,
    UnsupportedDayCountError,
    calculate_year_fraction,
    resolve_day_count_convention,
    supported_day_count_conventions,
)


def _business_calendar(**overrides: object) -> BusinessDayCalendar:
    values: dict[str, object] = {
        "calendar_id": "BRBD",
        "calendar_version": "2026.1",
        "valid_from": date(2026, 1, 1),
        "valid_to": date(2026, 12, 31),
        "business_dates": frozenset(
            {
                date(2026, 7, 13),
                date(2026, 7, 14),
                date(2026, 7, 15),
                date(2026, 7, 17),
            }
        ),
        "source_system": "official_calendar_source",
        "source_revision": "BRBD-2026-r3",
    }
    values.update(overrides)
    return BusinessDayCalendar(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("convention", "period_start", "period_end", "expected"),
    [
        ("ACT/365.FIXED", date(2023, 7, 1), date(2024, 7, 1), Decimal(366) / 365),
        ("ACT/365.FIXED", date(2024, 2, 28), date(2024, 3, 1), Decimal(2) / 365),
        ("ACT/360", date(2024, 2, 28), date(2024, 3, 1), Decimal(2) / 360),
        ("ACT/360", date(2026, 7, 18), date(2026, 7, 18), Decimal(0)),
    ],
)
def test_actual_conventions_use_elapsed_calendar_days_and_fixed_denominator(
    convention: str,
    period_start: date,
    period_end: date,
    expected: Decimal,
) -> None:
    assert (
        calculate_year_fraction(
            convention=convention,
            convention_version=1,
            inputs=DayCountInputs(period_start=period_start, period_end=period_end),
        )
        == expected
    )


def test_business_252_counts_start_inclusive_end_exclusive_calendar_facts() -> None:
    result = calculate_year_fraction(
        convention="BUS/252",
        convention_version=1,
        inputs=DayCountInputs(
            period_start=date(2026, 7, 13),
            period_end=date(2026, 7, 18),
            business_day_calendar=_business_calendar(),
        ),
    )

    assert result == Decimal(4) / 252


def test_business_252_requires_complete_authoritative_calendar_coverage() -> None:
    inputs = DayCountInputs(period_start=date(2026, 7, 13), period_end=date(2026, 7, 18))
    with pytest.raises(UnsupportedDayCountError, match="authoritative business-day calendar"):
        calculate_year_fraction(convention="BUS/252", convention_version=1, inputs=inputs)

    with pytest.raises(UnsupportedDayCountError, match="does not cover"):
        calculate_year_fraction(
            convention="BUS/252",
            convention_version=1,
            inputs=DayCountInputs(
                period_start=date(2026, 7, 13),
                period_end=date(2026, 7, 18),
                business_day_calendar=_business_calendar(valid_to=date(2026, 7, 17)),
            ),
        )


@pytest.mark.parametrize(
    ("period_start", "period_end", "expected_days"),
    [
        (date(2006, 2, 28), date(2006, 3, 31), 30),
        (date(2024, 2, 29), date(2024, 3, 31), 30),
        (date(2024, 2, 28), date(2024, 3, 31), 33),
        (date(2026, 1, 31), date(2026, 2, 28), 28),
    ],
)
def test_thirty_360_us_applies_sifma_end_of_february_and_31st_rules(
    period_start: date,
    period_end: date,
    expected_days: int,
) -> None:
    assert (
        calculate_year_fraction(
            convention="30/360.US",
            convention_version=1,
            inputs=DayCountInputs(period_start=period_start, period_end=period_end),
        )
        == Decimal(expected_days) / 360
    )


@pytest.mark.parametrize(
    ("period_start", "period_end", "expected_days"),
    [
        (date(2026, 2, 28), date(2026, 3, 31), 32),
        (date(2026, 1, 31), date(2026, 2, 28), 28),
        (date(2026, 1, 31), date(2026, 3, 31), 60),
    ],
)
def test_thirty_e_360_adjusts_only_31st_dates(
    period_start: date,
    period_end: date,
    expected_days: int,
) -> None:
    assert (
        calculate_year_fraction(
            convention="30E/360",
            convention_version=1,
            inputs=DayCountInputs(period_start=period_start, period_end=period_end),
        )
        == Decimal(expected_days) / 360
    )


def test_thirty_e_360_isda_preserves_february_contractual_termination() -> None:
    period_start = date(2023, 8, 31)
    period_end = date(2024, 2, 29)

    termination_fraction = calculate_year_fraction(
        convention="30E/360.ISDA",
        convention_version=1,
        inputs=DayCountInputs(
            period_start=period_start,
            period_end=period_end,
            contractual_termination_date=period_end,
        ),
    )
    ordinary_fraction = calculate_year_fraction(
        convention="30E/360.ISDA",
        convention_version=1,
        inputs=DayCountInputs(
            period_start=period_start,
            period_end=period_end,
            contractual_termination_date=date(2027, 2, 28),
        ),
    )

    assert termination_fraction == Decimal(179) / 360
    assert ordinary_fraction == Decimal(180) / 360


def test_thirty_e_360_isda_adjusts_last_day_of_february_when_not_termination() -> None:
    assert (
        calculate_year_fraction(
            convention="30E/360.ISDA",
            convention_version=1,
            inputs=DayCountInputs(
                period_start=date(2026, 2, 28),
                period_end=date(2026, 3, 31),
                contractual_termination_date=date(2028, 2, 29),
            ),
        )
        == Decimal(30) / 360
    )


def test_thirty_e_360_isda_requires_termination_date_source_fact() -> None:
    with pytest.raises(UnsupportedDayCountError, match="contractual termination date"):
        calculate_year_fraction(
            convention="30E/360.ISDA",
            convention_version=1,
            inputs=DayCountInputs(
                period_start=date(2026, 1, 31),
                period_end=date(2026, 7, 31),
            ),
        )


def test_registry_requires_exact_governed_code_and_version() -> None:
    definitions = supported_day_count_conventions()

    assert [(item.convention.value, item.convention_version) for item in definitions] == [
        ("ACT/365.FIXED", 1),
        ("ACT/360", 1),
        ("BUS/252", 1),
        ("30/360.US", 1),
        ("30E/360", 1),
        ("30E/360.ISDA", 1),
    ]
    assert resolve_day_count_convention(" act/360 ", 1).denominator == 360
    with pytest.raises(UnsupportedDayCountError, match="ACT/ACT@1"):
        resolve_day_count_convention("ACT/ACT", 1)
    with pytest.raises(UnsupportedDayCountError, match="ACT/360@2"):
        resolve_day_count_convention("ACT/360", 2)


def test_invalid_interval_and_calendar_lineage_fail_before_calculation() -> None:
    with pytest.raises(ValueError, match="period_end"):
        DayCountInputs(period_start=date(2026, 7, 18), period_end=date(2026, 7, 17))
    with pytest.raises(ValueError, match="source_revision"):
        _business_calendar(source_revision=" ")
    with pytest.raises(ValueError, match="validity window"):
        _business_calendar(business_dates=frozenset({date(2027, 1, 2)}))
    with pytest.raises(ValueError, match="cannot precede"):
        DayCountInputs(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 7, 1),
            contractual_termination_date=date(2026, 6, 30),
        )
