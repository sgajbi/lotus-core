"""Read-only SQL projection for fixed-income book-cost support evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from portfolio_common.database_models import (
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class FixedIncomeBookCostPeriodReadRecord:
    period_ordinal: int
    period_start_date: date
    period_end_date: date
    year_fraction: Decimal
    period_rate: Decimal
    begin_amortized_cost_local: Decimal
    interest_income_local: Decimal
    cash_coupon_local: Decimal
    amortization_amount_local: Decimal
    end_amortized_cost_local: Decimal
    rounding_adjustment_local: Decimal
    calculation_output_hash: str
    period_content_hash: str


@dataclass(frozen=True, slots=True)
class FixedIncomeBookCostProfileReadRecord:
    profile_id: str
    profile_version: int
    tenant_id: str
    legal_book_id: str
    portfolio_id: str
    security_id: str
    lot_id: str
    effective_date: date
    status: str
    eligibility_reason: str | None
    policy_id: str | None
    policy_version: int | None
    schedule_version: int | None
    currency: str | None
    direction: str | None
    initial_amortized_cost_local: Decimal | None
    redemption_value_local: Decimal | None
    final_amortized_cost_local: Decimal | None
    residual_local: Decimal | None
    authority_content_hash: str
    source_references: list[dict[str, Any]]
    calculation_lineage: dict[str, Any] | None
    profile_content_hash: str


@dataclass(frozen=True, slots=True)
class FixedIncomeBookCostAsOfReadRecord:
    profile: FixedIncomeBookCostProfileReadRecord
    periods: tuple[FixedIncomeBookCostPeriodReadRecord, ...]


class FixedIncomeBookCostReadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def effective_as_of(
        self,
        *,
        tenant_id: str,
        legal_book_id: str,
        portfolio_id: str,
        security_id: str,
        lot_id: str,
        as_of_date: date,
    ) -> FixedIncomeBookCostAsOfReadRecord | None:
        profile = (
            await self._db.scalars(
                select(LotAmortizedCostProfileRecord)
                .where(
                    LotAmortizedCostProfileRecord.tenant_id == tenant_id,
                    LotAmortizedCostProfileRecord.legal_book_id == legal_book_id,
                    LotAmortizedCostProfileRecord.portfolio_id == portfolio_id,
                    LotAmortizedCostProfileRecord.security_id == security_id,
                    LotAmortizedCostProfileRecord.lot_id == lot_id,
                    LotAmortizedCostProfileRecord.effective_date <= as_of_date,
                )
                .order_by(
                    LotAmortizedCostProfileRecord.effective_date.desc(),
                    LotAmortizedCostProfileRecord.profile_version.desc(),
                )
                .limit(1)
            )
        ).first()
        if profile is None:
            return None
        periods = list(
            (
                await self._db.scalars(
                    select(LotAmortizedCostPeriodRecord)
                    .where(
                        LotAmortizedCostPeriodRecord.profile_id == profile.profile_id,
                        LotAmortizedCostPeriodRecord.profile_version == profile.profile_version,
                    )
                    .order_by(LotAmortizedCostPeriodRecord.period_ordinal.asc())
                )
            ).all()
        )
        return FixedIncomeBookCostAsOfReadRecord(
            profile=_profile_read_record(profile),
            periods=tuple(_period_read_record(period) for period in periods),
        )


def _profile_read_record(
    profile: LotAmortizedCostProfileRecord,
) -> FixedIncomeBookCostProfileReadRecord:
    return FixedIncomeBookCostProfileReadRecord(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        tenant_id=profile.tenant_id,
        legal_book_id=profile.legal_book_id,
        portfolio_id=profile.portfolio_id,
        security_id=profile.security_id,
        lot_id=profile.lot_id,
        effective_date=profile.effective_date,
        status=profile.status,
        eligibility_reason=profile.eligibility_reason,
        policy_id=profile.policy_id,
        policy_version=profile.policy_version,
        schedule_version=profile.schedule_version,
        currency=profile.currency,
        direction=profile.direction,
        initial_amortized_cost_local=profile.initial_amortized_cost_local,
        redemption_value_local=profile.redemption_value_local,
        final_amortized_cost_local=profile.final_amortized_cost_local,
        residual_local=profile.residual_local,
        authority_content_hash=profile.authority_content_hash,
        source_references=[
            dict(item) for item in cast(list[dict[str, Any]], profile.source_references)
        ],
        calculation_lineage=(
            dict(cast(dict[str, Any], profile.calculation_lineage))
            if profile.calculation_lineage is not None
            else None
        ),
        profile_content_hash=profile.profile_content_hash,
    )


def _period_read_record(
    period: LotAmortizedCostPeriodRecord,
) -> FixedIncomeBookCostPeriodReadRecord:
    return FixedIncomeBookCostPeriodReadRecord(
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
