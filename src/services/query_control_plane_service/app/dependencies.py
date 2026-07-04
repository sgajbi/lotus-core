from fastapi import Depends
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsTimeseriesService,
)
from src.services.query_service.app.services.simulation_service import SimulationService


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(db)


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(db)
