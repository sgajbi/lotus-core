"""Segmented gross contractual accrued-income policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from .day_count import (
    BusinessDayCalendar,
    DayCountInputs,
    IcmaReferencePeriod,
    calculate_year_fraction,
)


class UnsupportedAccruedIncomeError(ValueError):
    """Raised when source segments cannot support deterministic accrued income."""


ACCRUED_INCOME_INTERMEDIATE_PRECISION = 50


class AccrualRateType(StrEnum):
    """Origin of the all-in annual rate supplied for an accrual segment."""

    FIXED = "FIXED"
    FLOATING_SUPPLIED = "FLOATING_SUPPLIED"


@dataclass(frozen=True, slots=True)
class AccrualSourceReference:
    """Source identity required for one contractual accrual fact."""

    source_system: str
    source_record_id: str
    source_revision: str

    def __post_init__(self) -> None:
        for field_name in ("source_system", "source_record_id", "source_revision"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be nonblank")


@dataclass(frozen=True, slots=True)
class AccrualSegment:
    """One interval over which principal, rate, and day-count facts are constant."""

    accrual_start: date
    accrual_end: date
    currency: str
    signed_accrual_principal: Decimal
    annual_effective_rate: Decimal
    rate_type: AccrualRateType
    day_count_convention: str
    day_count_convention_version: int
    rate_source: AccrualSourceReference
    principal_source: AccrualSourceReference
    schedule_source: AccrualSourceReference
    business_day_calendar: BusinessDayCalendar | None = None
    contractual_termination_date: date | None = None
    icma_reference_periods: tuple[IcmaReferencePeriod, ...] = ()

    def __post_init__(self) -> None:
        if self.accrual_end <= self.accrual_start:
            raise ValueError("accrual_end must be after accrual_start")
        if not self.currency.strip():
            raise ValueError("currency must be nonblank")
        if not self.signed_accrual_principal.is_finite():
            raise ValueError("signed_accrual_principal must be finite")
        if not self.annual_effective_rate.is_finite():
            raise ValueError("annual_effective_rate must be finite")
        if not self.day_count_convention.strip():
            raise ValueError("day_count_convention must be nonblank")
        if self.day_count_convention_version < 1:
            raise ValueError("day_count_convention_version must be positive")


@dataclass(frozen=True, slots=True)
class AccrualSegmentResult:
    """Auditable unrounded calculation result for one segment."""

    accrual_start: date
    accrual_end: date
    signed_accrual_principal: Decimal
    annual_effective_rate: Decimal
    year_fraction: Decimal
    accrued_income: Decimal
    rate_type: AccrualRateType
    rate_source: AccrualSourceReference
    principal_source: AccrualSourceReference
    schedule_source: AccrualSourceReference


@dataclass(frozen=True, slots=True)
class AccruedIncomeResult:
    """Gross contractual accrued income before any separately governed rounding."""

    currency: str
    gross_accrued_income: Decimal
    segments: tuple[AccrualSegmentResult, ...]


def calculate_segmented_accrued_income(
    segments: tuple[AccrualSegment, ...],
) -> AccruedIncomeResult:
    """Calculate contiguous principal/rate segments without frequency shortcuts."""

    if not segments:
        raise UnsupportedAccruedIncomeError("at least one accrual segment is required")
    ordered = tuple(sorted(segments, key=lambda item: (item.accrual_start, item.accrual_end)))
    _validate_contiguous_segments(ordered)
    currency = ordered[0].currency.strip().upper()
    if any(segment.currency.strip().upper() != currency for segment in ordered):
        raise UnsupportedAccruedIncomeError("accrual segments must use one currency")

    results: list[AccrualSegmentResult] = []
    gross_accrued_income = Decimal(0)
    for segment in ordered:
        year_fraction = calculate_year_fraction(
            convention=segment.day_count_convention,
            convention_version=segment.day_count_convention_version,
            inputs=DayCountInputs(
                period_start=segment.accrual_start,
                period_end=segment.accrual_end,
                business_day_calendar=segment.business_day_calendar,
                contractual_termination_date=segment.contractual_termination_date,
                icma_reference_periods=segment.icma_reference_periods,
            ),
        )
        with localcontext() as context:
            context.prec = ACCRUED_INCOME_INTERMEDIATE_PRECISION
            accrued_income = (
                segment.signed_accrual_principal * segment.annual_effective_rate * year_fraction
            )
            gross_accrued_income += accrued_income
        results.append(
            AccrualSegmentResult(
                accrual_start=segment.accrual_start,
                accrual_end=segment.accrual_end,
                signed_accrual_principal=segment.signed_accrual_principal,
                annual_effective_rate=segment.annual_effective_rate,
                year_fraction=year_fraction,
                accrued_income=accrued_income,
                rate_type=segment.rate_type,
                rate_source=segment.rate_source,
                principal_source=segment.principal_source,
                schedule_source=segment.schedule_source,
            )
        )
    return AccruedIncomeResult(
        currency=currency,
        gross_accrued_income=gross_accrued_income,
        segments=tuple(results),
    )


def _validate_contiguous_segments(segments: tuple[AccrualSegment, ...]) -> None:
    previous = segments[0]
    for current in segments[1:]:
        if current.accrual_start != previous.accrual_end:
            relation = "overlap" if current.accrual_start < previous.accrual_end else "gap"
            raise UnsupportedAccruedIncomeError(
                f"accrual segments contain a {relation} between "
                f"{previous.accrual_end.isoformat()} and {current.accrual_start.isoformat()}"
            )
        previous = current
