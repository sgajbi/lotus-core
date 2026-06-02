from datetime import date

from fastapi import Depends
from portfolio_common.database_models import BusinessDate
from portfolio_common.db import get_async_db_session
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class BusinessCalendarRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_latest_business_date(self, calendar_code: str) -> date | None:
        stmt = select(func.max(BusinessDate.date)).where(
            BusinessDate.calendar_code == calendar_code
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


def get_business_calendar_repository(
    db: AsyncSession = Depends(get_async_db_session),
) -> BusinessCalendarRepository:
    return BusinessCalendarRepository(db)
