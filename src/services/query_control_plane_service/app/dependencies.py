from fastapi import Depends
from portfolio_common.db import get_async_db_session
from portfolio_common.runtime_providers import SystemClock, UuidIdGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsTimeseriesService,
)
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotDependencies,
    CoreSnapshotService,
)
from src.services.query_service.app.services.integration_service import (
    IntegrationService,
    IntegrationServiceDependencies,
)
from src.services.query_service.app.services.operations_service import (
    OperationsService,
    OperationsServiceDependencies,
)

from .application.simulation import SimulationService
from .infrastructure.simulation_store import (
    SqlAlchemySimulationBaselineReader,
    SqlAlchemySimulationStore,
)
from .infrastructure.simulation_unit_of_work import SqlAlchemySimulationUnitOfWork


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(db)


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(dependencies=CoreSnapshotDependencies.from_session(db))


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(dependencies=IntegrationServiceDependencies.from_session(db))


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(dependencies=OperationsServiceDependencies.from_session(db))


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(
        store=SqlAlchemySimulationStore(db),
        baseline_reader=SqlAlchemySimulationBaselineReader(db),
        unit_of_work=SqlAlchemySimulationUnitOfWork(db),
        clock=SystemClock(),
        id_generator=UuidIdGenerator(),
    )
