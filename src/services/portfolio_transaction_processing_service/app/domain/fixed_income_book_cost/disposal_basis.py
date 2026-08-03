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
AMORTIZED_COST_DISPOSAL_ALGORITHM_VERSION = 1


class AmortizedCostDisposalError(ValueError):
    """Raised when a profile cannot support a truthful disposal projection."""


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
    consumed_quantity: Decimal
    residual_quantity: Decimal
    current_cost_local: Decimal
    consumed_cost_local: Decimal
    residual_cost_local: Decimal
    fx_rate_to_base: Decimal
    consumed_cost_base: Decimal
    residual_cost_base: Decimal
    calculation_lineage: CalculationLineage


def allocate_recognized_lot_book_cost(
    profile: LotAmortizedCostProfileVersion,
    *,
    disposal_date: date,
    original_quantity: Decimal,
    consumed_quantity: Decimal,
    fx_rate_to_base: Decimal,
) -> RecognizedLotBookCost:
    """Allocate recognized periodic book cost without mutating original or tax-lot basis.

    Profiles recognize movement at their authoritative period boundaries. A daily schedule therefore
    produces daily carrying amounts, while a coupon-period schedule retains its opening carrying
    amount until that period closes. Partial disposal allocation is proportional to original lot
    quantity, with the residual calculated as the exact governed complement.
    """

    _require_active_profile(profile)
    _require_date(disposal_date, "disposal_date")
    if disposal_date < profile.effective_date:
        raise AmortizedCostDisposalError(
            "disposal_date must not precede the effective amortized-cost profile"
        )
    _require_positive_decimal(original_quantity, "original_quantity")
    _require_positive_decimal(consumed_quantity, "consumed_quantity")
    _require_positive_decimal(fx_rate_to_base, "fx_rate_to_base")
    if consumed_quantity > original_quantity:
        raise AmortizedCostDisposalError("consumed_quantity must not exceed original_quantity")

    current_cost_local, recognized_through_date = _recognized_cost_local(
        profile,
        disposal_date=disposal_date,
    )
    numeric_policy = COST_BASIS_STATE_LEDGER_OUTPUT_V1
    with numeric_policy.arithmetic_context():
        raw_consumed_cost_local = current_cost_local * consumed_quantity / original_quantity
    consumed_cost_local = numeric_policy.normalize(
        raw_consumed_cost_local,
        field_name="amortized_disposal_cost_local",
    )
    residual_cost_local = numeric_policy.subtract(
        current_cost_local,
        consumed_cost_local,
        field_name="amortized_residual_cost_local",
    )
    residual_quantity = numeric_policy.subtract(
        original_quantity,
        consumed_quantity,
        field_name="amortized_residual_quantity",
    )
    consumed_cost_base = numeric_policy.multiply(
        consumed_cost_local,
        fx_rate_to_base,
        field_name="amortized_disposal_cost_base",
    )
    residual_cost_base = numeric_policy.multiply(
        residual_cost_local,
        fx_rate_to_base,
        field_name="amortized_residual_cost_base",
    )
    profile_content_hash = profile.content_hash()
    output_payload = {
        "consumed_cost_base": consumed_cost_base,
        "consumed_cost_local": consumed_cost_local,
        "consumed_quantity": consumed_quantity,
        "current_cost_local": current_cost_local,
        "recognized_through_date": recognized_through_date,
        "residual_cost_base": residual_cost_base,
        "residual_cost_local": residual_cost_local,
        "residual_quantity": residual_quantity,
    }
    lineage = build_calculation_lineage(
        algorithm_id=AMORTIZED_COST_DISPOSAL_ALGORITHM_ID,
        algorithm_version=AMORTIZED_COST_DISPOSAL_ALGORITHM_VERSION,
        intermediate_precision=numeric_policy.working_precision,
        input_payload={
            "consumed_quantity": consumed_quantity,
            "disposal_date": disposal_date,
            "fx_rate_to_base": fx_rate_to_base,
            "original_quantity": original_quantity,
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
        consumed_quantity=consumed_quantity,
        residual_quantity=residual_quantity,
        current_cost_local=current_cost_local,
        consumed_cost_local=consumed_cost_local,
        residual_cost_local=residual_cost_local,
        fx_rate_to_base=fx_rate_to_base,
        consumed_cost_base=consumed_cost_base,
        residual_cost_base=residual_cost_base,
        calculation_lineage=lineage,
    )


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
