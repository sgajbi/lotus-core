"""Project effective-dated amortized book cost into one lot disposal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.transaction.numeric_policy import (
    COST_BASIS_STATE_LEDGER_OUTPUT_V1,
)

from .policy import AmortizedCostProfileStatus
from .profile import LotAmortizedCostProfileVersion

AMORTIZED_COST_DISPOSAL_ALGORITHM_ID = "fixed-income-amortized-cost-disposal"
AMORTIZED_COST_DISPOSAL_ALGORITHM_VERSION = 2


class AmortizedCostDisposalError(ValueError):
    """Raised when a profile cannot support a truthful disposal projection."""


@dataclass(frozen=True, slots=True)
class CarriedLotBookCost:
    """Persisted carrying amount retained by the preceding partial disposal."""

    scheduled_cost_local: Decimal
    residual_cost_local: Decimal
    residual_cost_base: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "scheduled_cost_local",
            "residual_cost_local",
            "residual_cost_base",
        ):
            _require_non_negative_decimal(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class RecognizedLotBookCost:
    """Current carrying amount and proportional disposal evidence for one source lot."""

    profile_id: str
    profile_version: int
    profile_content_hash: str
    currency: str
    disposal_date: date
    recognized_through_date: date
    original_quantity: Decimal
    open_quantity_before: Decimal
    consumed_quantity: Decimal
    residual_quantity: Decimal
    scheduled_cost_local: Decimal
    current_cost_local: Decimal
    current_cost_base: Decimal
    consumed_cost_local: Decimal
    residual_cost_local: Decimal
    book_cost_fx_rate_to_base: Decimal
    consumed_cost_base: Decimal
    residual_cost_base: Decimal
    retained_rounding_residual_local: Decimal
    retained_rounding_residual_base: Decimal
    calculation_lineage: CalculationLineage

    def carry_forward(self) -> CarriedLotBookCost | None:
        """Return the exact open-lot state required by a later disposal."""

        if self.residual_quantity == Decimal(0):
            return None
        return CarriedLotBookCost(
            scheduled_cost_local=self.scheduled_cost_local,
            residual_cost_local=self.residual_cost_local,
            residual_cost_base=self.residual_cost_base,
        )


def allocate_recognized_lot_book_cost(
    profile: LotAmortizedCostProfileVersion,
    *,
    disposal_date: date,
    original_quantity: Decimal,
    open_quantity_before: Decimal,
    consumed_quantity: Decimal,
    book_cost_fx_rate_to_base: Decimal,
    carried_book_cost: CarriedLotBookCost | None = None,
) -> RecognizedLotBookCost:
    """Allocate recognized periodic book cost without mutating original or tax-lot basis.

    Profiles recognize movement at their authoritative period boundaries. A daily schedule therefore
    produces daily carrying amounts, while a coupon-period schedule retains its opening carrying
    amount until that period closes. Partial disposal allocation is proportional to original lot
    quantity, with the residual calculated as the exact governed complement. A later disposal
    starts from the preceding persisted residual and applies only the newly recognized schedule
    movement. This preserves decimal residuals without freezing later amortization or accretion.
    Base carrying cost is conserved independently using the source lot's governed book-cost
    conversion rate; it must not be substituted with disposal-date FX because capital and FX P&L
    are separate accounting effects.
    """

    _require_active_profile(profile)
    _require_date(disposal_date, "disposal_date")
    if disposal_date < profile.effective_date:
        raise AmortizedCostDisposalError(
            "disposal_date must not precede the effective amortized-cost profile"
        )
    _require_positive_decimal(original_quantity, "original_quantity")
    _require_positive_decimal(open_quantity_before, "open_quantity_before")
    _require_positive_decimal(consumed_quantity, "consumed_quantity")
    _require_positive_decimal(book_cost_fx_rate_to_base, "book_cost_fx_rate_to_base")
    if carried_book_cost is not None and not isinstance(carried_book_cost, CarriedLotBookCost):
        raise TypeError("carried_book_cost must be a CarriedLotBookCost or None")
    if open_quantity_before > original_quantity:
        raise AmortizedCostDisposalError("open_quantity_before must not exceed original_quantity")
    if consumed_quantity > open_quantity_before:
        raise AmortizedCostDisposalError("consumed_quantity must not exceed open_quantity_before")

    scheduled_cost_local, recognized_through_date = _recognized_cost_local(
        profile,
        disposal_date=disposal_date,
    )
    numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    current_cost_local, current_cost_base = _current_carried_cost(
        scheduled_cost_local=scheduled_cost_local,
        original_quantity=original_quantity,
        open_quantity_before=open_quantity_before,
        book_cost_fx_rate_to_base=book_cost_fx_rate_to_base,
        carried_book_cost=carried_book_cost,
    )
    if consumed_quantity == open_quantity_before:
        consumed_cost_local = current_cost_local
        consumed_cost_base = current_cost_base
    else:
        consumed_cost_local = _proportional_local_cost(
            scheduled_cost_local=scheduled_cost_local,
            quantity=consumed_quantity,
            original_quantity=original_quantity,
            field_name="amortized_disposal_cost_local",
        )
        consumed_cost_base = numeric_policy.multiply(
            consumed_cost_local,
            book_cost_fx_rate_to_base,
            field_name="amortized_disposal_cost_base",
        )
    residual_cost_local = numeric_policy.subtract(
        current_cost_local,
        consumed_cost_local,
        field_name="amortized_residual_cost_local",
    )
    residual_quantity = numeric_policy.subtract(
        open_quantity_before,
        consumed_quantity,
        field_name="amortized_residual_quantity",
    )
    residual_cost_base = numeric_policy.subtract(
        current_cost_base,
        consumed_cost_base,
        field_name="amortized_residual_cost_base",
    )
    scheduled_residual_cost_local = _proportional_local_cost(
        scheduled_cost_local=scheduled_cost_local,
        quantity=residual_quantity,
        original_quantity=original_quantity,
        field_name="amortized_scheduled_residual_cost_local",
    )
    scheduled_residual_cost_base = numeric_policy.multiply(
        scheduled_residual_cost_local,
        book_cost_fx_rate_to_base,
        field_name="amortized_scheduled_residual_cost_base",
    )
    retained_rounding_residual_local = numeric_policy.subtract(
        residual_cost_local,
        scheduled_residual_cost_local,
        field_name="amortized_retained_rounding_residual_local",
    )
    retained_rounding_residual_base = numeric_policy.subtract(
        residual_cost_base,
        scheduled_residual_cost_base,
        field_name="amortized_retained_rounding_residual_base",
    )
    profile_content_hash = profile.content_hash()
    output_payload = {
        "consumed_cost_base": consumed_cost_base,
        "consumed_cost_local": consumed_cost_local,
        "consumed_quantity": consumed_quantity,
        "current_cost_base": current_cost_base,
        "current_cost_local": current_cost_local,
        "open_quantity_before": open_quantity_before,
        "recognized_through_date": recognized_through_date,
        "residual_cost_base": residual_cost_base,
        "residual_cost_local": residual_cost_local,
        "residual_quantity": residual_quantity,
        "retained_rounding_residual_base": retained_rounding_residual_base,
        "retained_rounding_residual_local": retained_rounding_residual_local,
        "scheduled_cost_local": scheduled_cost_local,
    }
    lineage = build_calculation_lineage(
        algorithm_id=AMORTIZED_COST_DISPOSAL_ALGORITHM_ID,
        algorithm_version=AMORTIZED_COST_DISPOSAL_ALGORITHM_VERSION,
        intermediate_precision=numeric_policy.working_precision,
        input_payload={
            "consumed_quantity": consumed_quantity,
            "disposal_date": disposal_date,
            "book_cost_fx_rate_to_base": book_cost_fx_rate_to_base,
            "carried_book_cost": (
                {
                    "residual_cost_base": carried_book_cost.residual_cost_base,
                    "residual_cost_local": carried_book_cost.residual_cost_local,
                    "scheduled_cost_local": carried_book_cost.scheduled_cost_local,
                }
                if carried_book_cost is not None
                else None
            ),
            "original_quantity": original_quantity,
            "open_quantity_before": open_quantity_before,
            "profile_content_hash": profile_content_hash,
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "schedule_calculation_output_hash": (
                profile.calculation_lineage.output_content_hash
                if profile.calculation_lineage is not None
                else None
            ),
        },
        output_payload=output_payload,
        numeric_output_policy=numeric_policy.lineage_identity(),
    )
    return RecognizedLotBookCost(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_content_hash=profile_content_hash,
        currency=profile.currency or "",
        disposal_date=disposal_date,
        recognized_through_date=recognized_through_date,
        original_quantity=original_quantity,
        open_quantity_before=open_quantity_before,
        consumed_quantity=consumed_quantity,
        residual_quantity=residual_quantity,
        scheduled_cost_local=scheduled_cost_local,
        current_cost_local=current_cost_local,
        current_cost_base=current_cost_base,
        consumed_cost_local=consumed_cost_local,
        residual_cost_local=residual_cost_local,
        book_cost_fx_rate_to_base=book_cost_fx_rate_to_base,
        consumed_cost_base=consumed_cost_base,
        residual_cost_base=residual_cost_base,
        retained_rounding_residual_local=retained_rounding_residual_local,
        retained_rounding_residual_base=retained_rounding_residual_base,
        calculation_lineage=lineage,
    )


def _current_carried_cost(
    *,
    scheduled_cost_local: Decimal,
    original_quantity: Decimal,
    open_quantity_before: Decimal,
    book_cost_fx_rate_to_base: Decimal,
    carried_book_cost: CarriedLotBookCost | None,
) -> tuple[Decimal, Decimal]:
    policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    if carried_book_cost is None:
        current_local = _proportional_local_cost(
            scheduled_cost_local=scheduled_cost_local,
            quantity=open_quantity_before,
            original_quantity=original_quantity,
            field_name="amortized_open_cost_local",
        )
        return (
            current_local,
            policy.multiply(
                current_local,
                book_cost_fx_rate_to_base,
                field_name="amortized_open_cost_base",
            ),
        )

    schedule_movement_local = policy.subtract(
        scheduled_cost_local,
        carried_book_cost.scheduled_cost_local,
        field_name="amortized_schedule_movement_local",
    )
    recognized_movement_local = _proportional_local_cost(
        scheduled_cost_local=schedule_movement_local,
        quantity=open_quantity_before,
        original_quantity=original_quantity,
        field_name="amortized_open_schedule_movement_local",
    )
    recognized_movement_base = policy.multiply(
        recognized_movement_local,
        book_cost_fx_rate_to_base,
        field_name="amortized_open_schedule_movement_base",
    )
    current_local = policy.add(
        carried_book_cost.residual_cost_local,
        recognized_movement_local,
        field_name="amortized_open_cost_local",
    )
    current_base = policy.add(
        carried_book_cost.residual_cost_base,
        recognized_movement_base,
        field_name="amortized_open_cost_base",
    )
    if current_local < Decimal(0) or current_base < Decimal(0):
        raise AmortizedCostDisposalError(
            "recognized schedule movement must not reduce the open carrying amount below zero"
        )
    return current_local, current_base


def _proportional_local_cost(
    *,
    scheduled_cost_local: Decimal,
    quantity: Decimal,
    original_quantity: Decimal,
    field_name: str,
) -> Decimal:
    policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    with policy.arithmetic_context():
        raw_cost = scheduled_cost_local * quantity / original_quantity
    return policy.normalize(raw_cost, field_name=field_name)


def _recognized_cost_local(
    profile: LotAmortizedCostProfileVersion,
    *,
    disposal_date: date,
) -> tuple[Decimal, date]:
    initial = profile.initial_amortized_cost_local
    if initial is None:
        raise AmortizedCostDisposalError("active profile is missing initial amortized cost")
    recognized_cost = initial
    recognized_through_date = profile.effective_date
    for period in profile.periods:
        if period.period_end_date > disposal_date:
            break
        recognized_cost = period.end_amortized_cost_local
        recognized_through_date = period.period_end_date
    return recognized_cost, recognized_through_date


def _require_active_profile(profile: object) -> None:
    if not isinstance(profile, LotAmortizedCostProfileVersion):
        raise TypeError("profile must be a LotAmortizedCostProfileVersion")
    if profile.status is not AmortizedCostProfileStatus.ACTIVE:
        raise AmortizedCostDisposalError("amortized-cost disposal requires an ACTIVE profile")


def _require_date(value: object, field_name: str) -> None:
    if type(value) is not date:
        raise TypeError(f"{field_name} must be a date")


def _require_positive_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_decimal(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
