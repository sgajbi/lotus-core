"""Versioned day-count policies for contractual accrued-income calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


class UnsupportedDayCountError(ValueError):
    """Raised when source facts cannot support an exact day-count policy."""


class DayCountConvention(StrEnum):
    """Implemented source convention codes aligned to the FpML vocabulary."""

    ACTUAL_365_FIXED = "ACT/365.FIXED"
    ACTUAL_360 = "ACT/360"
    BUSINESS_252 = "BUS/252"
    THIRTY_360_US = "30/360.US"
    THIRTY_E_360 = "30E/360"
    THIRTY_E_360_ISDA = "30E/360.ISDA"


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
class DayCountInputs:
    """Contractual interval and optional calendar evidence for one calculation."""

    period_start: date
    period_end: date
    business_day_calendar: BusinessDayCalendar | None = None
    contractual_termination_date: date | None = None

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
    denominator: int
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
    return Decimal(numerator) / Decimal(definition.denominator)


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
