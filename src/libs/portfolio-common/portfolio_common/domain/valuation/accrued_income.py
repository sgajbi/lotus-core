"""Segmented gross contractual accrued-income policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from .calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    build_calculation_lineage,
)
from .day_count import (
    BusinessDayCalendar,
    DayCountInputs,
    IcmaReferencePeriod,
    calculate_year_fraction,
)


class UnsupportedAccruedIncomeError(ValueError):
    """Raised when source segments cannot support deterministic accrued income."""


ACCRUED_INCOME_INTERMEDIATE_PRECISION = 50
ACCRUED_INCOME_ALGORITHM_ID = "SEGMENTED_GROSS_CONTRACTUAL_ACCRUAL"
ACCRUED_INCOME_ALGORITHM_VERSION = 2


class AccrualRateType(StrEnum):
    """Origin of the all-in annual rate supplied for an accrual segment."""

    FIXED = "FIXED"
    FLOATING_SUPPLIED = "FLOATING_SUPPLIED"


AccrualSourceReference = FinancialSourceReference


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
class ExCouponEntitlement:
    """Source-owned loss of entitlement to the next contractual coupon."""

    ex_coupon_date: date
    next_coupon_payment_date: date
    full_coupon_segments: tuple[AccrualSegment, ...]
    entitlement_source: AccrualSourceReference

    def __post_init__(self) -> None:
        if self.next_coupon_payment_date <= self.ex_coupon_date:
            raise ValueError("next_coupon_payment_date must be after ex_coupon_date")
        if not self.full_coupon_segments:
            raise ValueError("full_coupon_segments must not be empty")


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
    ex_coupon_entitlement_adjustment: Decimal
    settlement_accrued_income: Decimal
    segments: tuple[AccrualSegmentResult, ...]
    lineage: CalculationLineage


def calculate_segmented_accrued_income(
    segments: tuple[AccrualSegment, ...],
    *,
    ex_coupon_entitlement: ExCouponEntitlement | None = None,
) -> AccruedIncomeResult:
    """Calculate contractual accrual and any explicit ex-coupon settlement rebate."""

    if not segments:
        raise UnsupportedAccruedIncomeError("at least one accrual segment is required")
    ordered = tuple(sorted(segments, key=lambda item: (item.accrual_start, item.accrual_end)))
    _validate_contiguous_segments(ordered)
    currency = ordered[0].currency.strip().upper()
    if any(segment.currency.strip().upper() != currency for segment in ordered):
        raise UnsupportedAccruedIncomeError("accrual segments must use one currency")

    result_segments, gross_accrued_income = _calculate_segments(ordered)
    ex_coupon_entitlement_adjustment = Decimal(0)
    entitlement_payload: dict[str, object] | None = None
    if ex_coupon_entitlement is not None:
        full_coupon_segments = tuple(
            sorted(
                ex_coupon_entitlement.full_coupon_segments,
                key=lambda item: (item.accrual_start, item.accrual_end),
            )
        )
        _validate_ex_coupon_entitlement(
            accrued_segments=ordered,
            full_coupon_segments=full_coupon_segments,
            entitlement=ex_coupon_entitlement,
            currency=currency,
        )
        _, ex_coupon_entitlement_adjustment = _calculate_segments(full_coupon_segments)
        entitlement_payload = {
            "entitlement_source": _source_payload(ex_coupon_entitlement.entitlement_source),
            "ex_coupon_date": ex_coupon_entitlement.ex_coupon_date,
            "full_coupon_segments": [
                _segment_input_payload(segment) for segment in full_coupon_segments
            ],
            "next_coupon_payment_date": ex_coupon_entitlement.next_coupon_payment_date,
        }
    with localcontext() as context:
        context.prec = ACCRUED_INCOME_INTERMEDIATE_PRECISION
        settlement_accrued_income = gross_accrued_income - ex_coupon_entitlement_adjustment
    lineage = build_calculation_lineage(
        algorithm_id=ACCRUED_INCOME_ALGORITHM_ID,
        algorithm_version=ACCRUED_INCOME_ALGORITHM_VERSION,
        intermediate_precision=ACCRUED_INCOME_INTERMEDIATE_PRECISION,
        input_payload={
            "ex_coupon_entitlement": entitlement_payload,
            "segments": [_segment_input_payload(segment) for segment in ordered],
        },
        output_payload={
            "currency": currency,
            "ex_coupon_entitlement_adjustment": ex_coupon_entitlement_adjustment,
            "gross_accrued_income": gross_accrued_income,
            "segments": [_segment_output_payload(result) for result in result_segments],
            "settlement_accrued_income": settlement_accrued_income,
        },
    )
    return AccruedIncomeResult(
        currency=currency,
        gross_accrued_income=gross_accrued_income,
        ex_coupon_entitlement_adjustment=ex_coupon_entitlement_adjustment,
        settlement_accrued_income=settlement_accrued_income,
        segments=result_segments,
        lineage=lineage,
    )


def _calculate_segments(
    segments: tuple[AccrualSegment, ...],
) -> tuple[tuple[AccrualSegmentResult, ...], Decimal]:
    results: list[AccrualSegmentResult] = []
    gross_accrued_income = Decimal(0)
    for segment in segments:
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
    return tuple(results), gross_accrued_income


def _validate_ex_coupon_entitlement(
    *,
    accrued_segments: tuple[AccrualSegment, ...],
    full_coupon_segments: tuple[AccrualSegment, ...],
    entitlement: ExCouponEntitlement,
    currency: str,
) -> None:
    _validate_contiguous_segments(full_coupon_segments)
    if any(segment.currency.strip().upper() != currency for segment in full_coupon_segments):
        raise UnsupportedAccruedIncomeError(
            "full coupon and accrued segments must use one currency"
        )
    settlement_date = accrued_segments[-1].accrual_end
    if settlement_date <= entitlement.ex_coupon_date:
        raise UnsupportedAccruedIncomeError(
            "ex-coupon treatment requires settlement after ex_coupon_date"
        )
    if settlement_date >= entitlement.next_coupon_payment_date:
        raise UnsupportedAccruedIncomeError(
            "ex-coupon treatment requires settlement before next_coupon_payment_date"
        )
    if full_coupon_segments[0].accrual_start != accrued_segments[0].accrual_start:
        raise UnsupportedAccruedIncomeError(
            "full coupon and accrued segments must share the coupon-period start"
        )
    if full_coupon_segments[-1].accrual_end != entitlement.next_coupon_payment_date:
        raise UnsupportedAccruedIncomeError(
            "full coupon segments must end on next_coupon_payment_date"
        )
    _validate_accrued_prefix_matches_full_coupon(accrued_segments, full_coupon_segments)


def _validate_accrued_prefix_matches_full_coupon(
    accrued_segments: tuple[AccrualSegment, ...],
    full_coupon_segments: tuple[AccrualSegment, ...],
) -> None:
    full_index = 0
    for accrued in accrued_segments:
        cursor = accrued.accrual_start
        while cursor < accrued.accrual_end:
            while (
                full_index < len(full_coupon_segments)
                and full_coupon_segments[full_index].accrual_end <= cursor
            ):
                full_index += 1
            if full_index >= len(full_coupon_segments):
                raise UnsupportedAccruedIncomeError(
                    "accrued segments must be covered by full coupon segments"
                )
            full = full_coupon_segments[full_index]
            if full.accrual_start > cursor or _segment_terms(accrued) != _segment_terms(full):
                raise UnsupportedAccruedIncomeError(
                    "accrued segments must be an economic prefix of full coupon segments"
                )
            cursor = min(accrued.accrual_end, full.accrual_end)


def _segment_terms(segment: AccrualSegment) -> tuple[object, ...]:
    return (
        segment.currency.strip().upper(),
        segment.signed_accrual_principal,
        segment.annual_effective_rate,
        segment.rate_type,
        segment.day_count_convention.strip().upper(),
        segment.day_count_convention_version,
        segment.rate_source,
        segment.principal_source,
        segment.schedule_source,
        segment.business_day_calendar,
        segment.contractual_termination_date,
        segment.icma_reference_periods,
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


def _segment_input_payload(segment: AccrualSegment) -> dict[str, object]:
    calendar = segment.business_day_calendar
    return {
        "accrual_end": segment.accrual_end,
        "accrual_start": segment.accrual_start,
        "annual_effective_rate": segment.annual_effective_rate,
        "business_day_calendar": (
            {
                "calendar_content_hash": calendar.calendar_content_hash,
                "calendar_id": calendar.calendar_id.strip(),
                "calendar_version": calendar.calendar_version.strip(),
                "source_revision": calendar.source_revision.strip(),
                "source_system": calendar.source_system.strip(),
                "valid_from": calendar.valid_from,
                "valid_to": calendar.valid_to,
            }
            if calendar is not None
            else None
        ),
        "contractual_termination_date": segment.contractual_termination_date,
        "currency": segment.currency.strip().upper(),
        "day_count_convention": segment.day_count_convention.strip().upper(),
        "day_count_convention_version": segment.day_count_convention_version,
        "icma_reference_periods": [
            {
                "coupon_frequency_per_year": reference.coupon_frequency_per_year,
                "reference_end": reference.reference_end,
                "reference_start": reference.reference_start,
            }
            for reference in segment.icma_reference_periods
        ],
        "principal_source": _source_payload(segment.principal_source),
        "rate_source": _source_payload(segment.rate_source),
        "rate_type": segment.rate_type,
        "schedule_source": _source_payload(segment.schedule_source),
        "signed_accrual_principal": segment.signed_accrual_principal,
    }


def _segment_output_payload(result: AccrualSegmentResult) -> dict[str, object]:
    return {
        "accrual_end": result.accrual_end,
        "accrual_start": result.accrual_start,
        "accrued_income": result.accrued_income,
        "annual_effective_rate": result.annual_effective_rate,
        "rate_type": result.rate_type,
        "signed_accrual_principal": result.signed_accrual_principal,
        "year_fraction": result.year_fraction,
    }


def _source_payload(source: AccrualSourceReference) -> dict[str, object]:
    return source.lineage_payload()
