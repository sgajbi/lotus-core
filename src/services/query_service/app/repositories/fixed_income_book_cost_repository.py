"""Read-only SQL projection for fixed-income book-cost support evidence."""

from __future__ import annotations

from datetime import date

from portfolio_common.database_models import (
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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
    ) -> tuple[LotAmortizedCostProfileRecord, list[LotAmortizedCostPeriodRecord]] | None:
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
        return profile, periods
