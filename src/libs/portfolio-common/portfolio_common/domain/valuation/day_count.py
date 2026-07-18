"""Versioned day-count policies for contractual accrued-income calculations."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType


class UnsupportedDayCountError(ValueError):
    """Raised when source facts cannot support an exact day-count policy."""


DAY_COUNT_INTERMEDIATE_PRECISION = 50


class DayCountConvention(StrEnum):
    """Implemented source convention codes aligned to the FpML vocabulary."""

    ACTUAL_365_FIXED = "ACT/365.FIXED"
    ACTUAL_360 = "ACT/360"
    BUSINESS_252 = "BUS/252"
    THIRTY_360_US = "30/360.US"
    THIRTY_E_360 = "30E/360"
    THIRTY_E_360_ISDA = "30E/360.ISDA"
    ACTUAL_ACTUAL_ISDA = "ACT/ACT.ISDA"
    ACTUAL_ACTUAL_ICMA = "ACT/ACT.ICMA"


@dataclass(frozen=True, slots=True)
class BusinessDayCalendar:
    """Source-owned business-day set with bounded coverage and version lineage."""

    calendar_id: str
    calendar_version: str
    valid_from: date
    valid_to: date
    business_dates: frozenset[date]
    source_system: str
    source_revision: str

    def __post_init__(self) -> None:
        for field_name in (
            "calendar_id",
            "calendar_version",
            "source_system",
            "source_revision",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be nonblank")
        if self.valid_to < self.valid_from:
            raise ValueError("calendar valid_to must be on or after valid_from")
        if any(day < self.valid_from or day > self.valid_to for day in self.business_dates):
            raise ValueError("business_dates must fall within the calendar validity window")


@dataclass(frozen=True, slots=True)
class IcmaReferencePeriod:
    """One authoritative regular or quasi-coupon reference period."""

    reference_start: date
    reference_end: date
    coupon_frequency_per_year: int

    def __post_init__(self) -> None:
        if self.reference_end <= self.reference_start:
            raise ValueError("reference_end must be after reference_start")
        if self.coupon_frequency_per_year < 1:
            raise ValueError("coupon_frequency_per_year must be positive")


@dataclass(frozen=True, slots=True)
class DayCountInputs:
    """Contractual interval and optional calendar evidence for one calculation."""

    period_start: date
    period_end: date
    business_day_calendar: BusinessDayCalendar | None = None
    contractual_termination_date: date | None = None
    icma_reference_periods: tuple[IcmaReferencePeriod, ...] = ()

    def __post_init__(self) -> None:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if (
            self.contractual_termination_date is not None
            and self.contractual_termination_date < self.period_end
        ):
            raise ValueError("contractual_termination_date cannot precede period_end")


@dataclass(frozen=True, slots=True)
class DayCountConventionDefinition:
    """One exact supported convention version and denominator basis."""

    convention: DayCountConvention
    convention_version: int
    denominator: int | None
    requires_business_day_calendar: bool


_CONVENTIONS = (
    DayCountConventionDefinition(
        convention=DayCountConvention.ACTUAL_365_FIXED,
        convention_version=1,
        denominator=365,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.ACTUAL_360,
        convention_version=1,
        denominator=360,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.BUSINESS_252,
        convention_version=1,
        denominator=252,
        requires_business_day_calendar=True,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.THIRTY_360_US,
        convention_version=1,
        denominator=360,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.THIRTY_E_360,
        convention_version=1,
        denominator=360,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.THIRTY_E_360_ISDA,
        convention_version=1,
        denominator=360,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.ACTUAL_ACTUAL_ISDA,
        convention_version=1,
        denominator=None,
        requires_business_day_calendar=False,
    ),
    DayCountConventionDefinition(
        convention=DayCountConvention.ACTUAL_ACTUAL_ICMA,
        convention_version=1,
        denominator=None,
        requires_business_day_calendar=False,
    ),
)
_CONVENTIONS_BY_KEY = MappingProxyType(
    {
        (definition.convention.value, definition.convention_version): definition
        for definition in _CONVENTIONS
    }
)
if len(_CONVENTIONS_BY_KEY) != len(_CONVENTIONS):
    raise RuntimeError("day-count registry contains duplicate convention/version keys")


def supported_day_count_conventions() -> tuple[DayCountConventionDefinition, ...]:
    """Return the immutable implemented convention catalog in stable order."""

    return _CONVENTIONS


def resolve_day_count_convention(
    convention: str,
    convention_version: int,
) -> DayCountConventionDefinition:
    """Resolve one exact convention/version without alias or latest-version fallback."""

    normalized_convention = convention.strip().upper()
    if not normalized_convention:
        raise ValueError("convention must be nonblank")
    if convention_version < 1:
        raise ValueError("convention_version must be positive")
    try:
        return _CONVENTIONS_BY_KEY[(normalized_convention, convention_version)]
    except KeyError as error:
        raise UnsupportedDayCountError(
            f"unsupported day-count convention: {normalized_convention}@{convention_version}"
        ) from error


def calculate_year_fraction(
    *,
    convention: str,
    convention_version: int,
    inputs: DayCountInputs,
) -> Decimal:
    """Calculate one exact start-inclusive/end-exclusive contractual year fraction."""

    definition = resolve_day_count_convention(convention, convention_version)
    if inputs.period_start == inputs.period_end:
        return Decimal(0)
    if definition.convention is DayCountConvention.ACTUAL_ACTUAL_ISDA:
        return _actual_actual_isda_fraction(inputs.period_start, inputs.period_end)
    if definition.convention is DayCountConvention.ACTUAL_ACTUAL_ICMA:
        return _actual_actual_icma_fraction(inputs)
    if definition.convention is DayCountConvention.THIRTY_360_US:
        numerator = _thirty_360_us_days(inputs.period_start, inputs.period_end)
    elif definition.convention is DayCountConvention.THIRTY_E_360:
        numerator = _thirty_e_360_days(inputs.period_start, inputs.period_end)
    elif definition.convention is DayCountConvention.THIRTY_E_360_ISDA:
        numerator = _thirty_e_360_isda_days(inputs)
    elif definition.requires_business_day_calendar:
        numerator = _business_day_count(inputs)
    else:
        numerator = (inputs.period_end - inputs.period_start).days
    if definition.denominator is None:
        raise RuntimeError("fixed-denominator convention is missing its denominator")
    return _ratio(numerator, definition.denominator)


def _business_day_count(inputs: DayCountInputs) -> int:
    calendar = inputs.business_day_calendar
    if calendar is None:
        raise UnsupportedDayCountError("BUS/252 requires an authoritative business-day calendar")
    if calendar.valid_from > inputs.period_start or calendar.valid_to < inputs.period_end:
        raise UnsupportedDayCountError(
            "business-day calendar does not cover the calculation interval"
        )
    return sum(
        inputs.period_start <= business_date < inputs.period_end
        for business_date in calendar.business_dates
    )


def _thirty_360_us_days(period_start: date, period_end: date) -> int:
    start_day = period_start.day
    if _is_last_day_of_february(period_start) or start_day == 31:
        start_day = 30
    end_day = period_end.day
    if start_day == 30 and end_day == 31:
        end_day = 30
    return _thirty_360_numerator(period_start, period_end, start_day, end_day)


def _thirty_e_360_days(period_start: date, period_end: date) -> int:
    start_day = min(period_start.day, 30)
    end_day = min(period_end.day, 30)
    return _thirty_360_numerator(period_start, period_end, start_day, end_day)


def _thirty_e_360_isda_days(inputs: DayCountInputs) -> int:
    termination_date = inputs.contractual_termination_date
    if termination_date is None:
        raise UnsupportedDayCountError("30E/360.ISDA requires the contractual termination date")
    period_start = inputs.period_start
    period_end = inputs.period_end
    start_day = 30 if _is_last_day_of_month(period_start) else period_start.day
    is_february_termination = period_end.month == 2 and period_end == termination_date
    end_day = period_end.day
    if _is_last_day_of_month(period_end) and not is_february_termination:
        end_day = 30
    return _thirty_360_numerator(period_start, period_end, start_day, end_day)


def _thirty_360_numerator(
    period_start: date,
    period_end: date,
    start_day: int,
    end_day: int,
) -> int:
    return (
        360 * (period_end.year - period_start.year)
        + 30 * (period_end.month - period_start.month)
        + end_day
        - start_day
    )


def _is_last_day_of_february(value: date) -> bool:
    return value.month == 2 and _is_last_day_of_month(value)


def _is_last_day_of_month(value: date) -> bool:
    if value.month == 12:
        return value.day == 31
    return value.day == (date(value.year, value.month + 1, 1) - date.resolution).day


def _actual_actual_isda_fraction(period_start: date, period_end: date) -> Decimal:
    with localcontext() as context:
        context.prec = DAY_COUNT_INTERMEDIATE_PRECISION
        fraction = Decimal(0)
        segment_start = period_start
        while segment_start < period_end:
            segment_end = (
                period_end
                if segment_start.year == period_end.year
                else date(segment_start.year + 1, 1, 1)
            )
            denominator = 366 if calendar.isleap(segment_start.year) else 365
            fraction += Decimal((segment_end - segment_start).days) / Decimal(denominator)
            segment_start = segment_end
        return +fraction


def _actual_actual_icma_fraction(inputs: DayCountInputs) -> Decimal:
    if not inputs.icma_reference_periods:
        raise UnsupportedDayCountError(
            "ACT/ACT.ICMA requires authoritative coupon reference periods"
        )
    with localcontext() as context:
        context.prec = DAY_COUNT_INTERMEDIATE_PRECISION
        fraction = Decimal(0)
        covered_until = inputs.period_start
        for reference in sorted(
            inputs.icma_reference_periods,
            key=lambda item: (item.reference_start, item.reference_end),
        ):
            overlap_start = max(inputs.period_start, reference.reference_start)
            overlap_end = min(inputs.period_end, reference.reference_end)
            if overlap_end <= overlap_start:
                continue
            if overlap_start != covered_until:
                raise UnsupportedDayCountError(
                    "ICMA reference periods must cover the calculation interval exactly once"
                )
            reference_days = (reference.reference_end - reference.reference_start).days
            overlap_days = (overlap_end - overlap_start).days
            fraction += Decimal(overlap_days) / Decimal(
                reference_days * reference.coupon_frequency_per_year
            )
            covered_until = overlap_end
        if covered_until != inputs.period_end:
            raise UnsupportedDayCountError(
                "ICMA reference periods must cover the calculation interval exactly once"
            )
        return +fraction


def _ratio(numerator: int, denominator: int) -> Decimal:
    with localcontext() as context:
        context.prec = DAY_COUNT_INTERMEDIATE_PRECISION
        return Decimal(numerator) / Decimal(denominator)
