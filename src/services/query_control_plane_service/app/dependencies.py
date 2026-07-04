from fastapi import Depends
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsTimeseriesService,
)
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotService,
)
from src.services.query_service.app.services.integration_service import IntegrationService
from src.services.query_service.app.services.operations_service import OperationsService
from src.services.query_service.app.services.simulation_service import SimulationService


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(db)


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(db)


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(db)
