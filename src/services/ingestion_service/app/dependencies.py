from fastapi import Depends
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from .repositories.business_calendar_repository import BusinessCalendarRepository
from .services.business_date_ingestion_policy import BusinessDateIngestionPolicy


def get_business_calendar_repository(
    db: AsyncSession = Depends(get_async_db_session),
) -> BusinessCalendarRepository:
    return BusinessCalendarRepository(db)


def get_business_date_ingestion_policy(
    business_calendar_repository: BusinessCalendarRepository = Depends(
        get_business_calendar_repository
    ),
) -> BusinessDateIngestionPolicy:
    return BusinessDateIngestionPolicy(business_calendar_repository)
