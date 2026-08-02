"""Build date-correct fixed-income book-cost supportability evidence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.fixed_income_book_cost_dto import (
    BookCostCalculationLineageResponse,
    BookCostPeriodRecognitionResponse,
    BookCostSourceReferenceResponse,
    FixedIncomeBookCostAsOfResponse,
)
from ..repositories.fixed_income_book_cost_repository import (
    FixedIncomeBookCostPeriodReadRecord,
    FixedIncomeBookCostProfileReadRecord,
    FixedIncomeBookCostReadRepository,
)


class FixedIncomeBookCostService:
    def __init__(self, db: AsyncSession) -> None:
        self._repository = FixedIncomeBookCostReadRepository(db)

    async def get_as_of(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        portfolio_id: str,
        security_id: str,
        lot_id: str,
        as_of_date: date,
    ) -> FixedIncomeBookCostAsOfResponse:
        scope = {
            "tenant_id": _normalized_identifier(tenant_id, "tenant_id"),
            "legal_book_id": _normalized_identifier(legal_book_id, "legal_book_id"),
            "portfolio_id": _normalized_identifier(portfolio_id, "portfolio_id"),
            "security_id": _normalized_identifier(security_id, "security_id"),
            "lot_id": _normalized_identifier(lot_id, "lot_id"),
        }
        result = await self._repository.effective_as_of(
            **scope,
            as_of_date=as_of_date,
        )
        if result is None:
            raise LookupError(
                "fixed-income book-cost profile not found for exact "
                "tenant/legal-book/portfolio/security/lot scope and as-of date"
            )
        return _response(
            profile=result.profile,
            periods=result.periods,
            as_of_date=as_of_date,
        )


def _response(
    *,
    profile: FixedIncomeBookCostProfileReadRecord,
    periods: tuple[FixedIncomeBookCostPeriodReadRecord, ...],
    as_of_date: date,
) -> FixedIncomeBookCostAsOfResponse:
    recognized = [period for period in periods if period.period_end_date <= as_of_date]
    latest = recognized[-1] if recognized else None
    next_period = next(
        (period for period in periods if period.period_end_date > as_of_date),
        None,
    )
    book_cost = (
        latest.end_amortized_cost_local
        if latest is not None
        else profile.initial_amortized_cost_local
    )
    return FixedIncomeBookCostAsOfResponse(
        tenant_id=profile.tenant_id,
        legal_book_id=profile.legal_book_id,
        portfolio_id=profile.portfolio_id,
        security_id=profile.security_id,
        lot_id=profile.lot_id,
        requested_as_of_date=as_of_date,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_effective_date=profile.effective_date,
        status=profile.status,
        eligibility_reason=profile.eligibility_reason,
        policy_id=profile.policy_id,
        policy_version=profile.policy_version,
        schedule_version=profile.schedule_version,
        currency=profile.currency,
        direction=profile.direction,
        book_cost_local_as_of=book_cost,
        recognized_through_date=latest.period_end_date if latest is not None else None,
        next_recognition_date=next_period.period_end_date if next_period is not None else None,
        recognized_period_count=len(recognized),
        total_period_count=len(periods),
        initial_amortized_cost_local=profile.initial_amortized_cost_local,
        redemption_value_local=profile.redemption_value_local,
        final_amortized_cost_local=profile.final_amortized_cost_local,
        residual_local=profile.residual_local,
        authority_content_hash=profile.authority_content_hash,
        profile_content_hash=profile.profile_content_hash,
        source_references=[
            BookCostSourceReferenceResponse.model_validate(item)
            for item in cast(list[object], profile.source_references)
        ],
        calculation_lineage=(
            BookCostCalculationLineageResponse.model_validate(profile.calculation_lineage)
            if profile.calculation_lineage is not None
            else None
        ),
        latest_recognized_period=_period_response(latest) if latest is not None else None,
    )


def _period_response(
    period: FixedIncomeBookCostPeriodReadRecord,
) -> BookCostPeriodRecognitionResponse:
    return BookCostPeriodRecognitionResponse(
        period_ordinal=period.period_ordinal,
        period_start_date=period.period_start_date,
        period_end_date=period.period_end_date,
        year_fraction=cast(Decimal, period.year_fraction),
        period_rate=period.period_rate,
        begin_amortized_cost_local=period.begin_amortized_cost_local,
        interest_income_local=period.interest_income_local,
        cash_coupon_local=period.cash_coupon_local,
        amortization_amount_local=period.amortization_amount_local,
        end_amortized_cost_local=period.end_amortized_cost_local,
        rounding_adjustment_local=period.rounding_adjustment_local,
        calculation_output_hash=period.calculation_output_hash,
        period_content_hash=period.period_content_hash,
    )


def _normalized_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized
