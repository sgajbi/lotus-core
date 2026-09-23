from datetime import date

from portfolio_common.business_calendar_sql import business_calendar_code_matches
from portfolio_common.database_models import BusinessDate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class BusinessCalendarRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_latest_business_date(self, calendar_code: str) -> date | None:
        stmt = select(func.max(BusinessDate.date)).where(
            business_calendar_code_matches(BusinessDate.calendar_code, calendar_code)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
