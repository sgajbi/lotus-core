from fastapi import Depends
from portfolio_common.db import get_async_db_session
from portfolio_common.runtime_providers import SystemClock, UuidIdGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.integration_service import (
    IntegrationService,
    IntegrationServiceDependencies,
)
from src.services.query_service.app.services.operations_service import (
    OperationsService,
    OperationsServiceDependencies,
)

from .application.analytics.analytics_timeseries_service import (
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from .application.core_snapshot.service import (
    CoreSnapshotDependencies,
    CoreSnapshotService,
)
from .application.simulation import SimulationService
from .infrastructure.analytics_export_repository import AnalyticsExportRepository
from .infrastructure.analytics_timeseries_repository import AnalyticsTimeseriesRepository
from .infrastructure.analytics_unit_of_work import SqlAlchemyAnalyticsUnitOfWork
from .infrastructure.core_snapshot_sources import SqlAlchemyCoreSnapshotSourceReader
from .infrastructure.simulation_store import (
    SqlAlchemySimulationBaselineReader,
    SqlAlchemySimulationStore,
)
from .infrastructure.simulation_unit_of_work import SqlAlchemySimulationUnitOfWork
from .settings import load_query_control_plane_settings


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    settings = load_query_control_plane_settings()
    return AnalyticsTimeseriesService(
        reader=AnalyticsTimeseriesRepository(db),
        export_store=AnalyticsExportRepository(db),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(db),
        policy=AnalyticsRuntimePolicy(
            page_token_secret=settings.page_token_secret,
            page_token_key_id=settings.page_token_key_id,
            page_token_previous_keys=settings.page_token_previous_keys,
            page_token_ttl_seconds=settings.page_token_ttl_seconds,
            export_stale_timeout_minutes=settings.analytics_export_stale_timeout_minutes,
            export_execution_timeout_seconds=settings.analytics_export_execution_timeout_seconds,
        ),
    )


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(
        dependencies=CoreSnapshotDependencies(
            source_reader=SqlAlchemyCoreSnapshotSourceReader(db),
            simulation_store=SqlAlchemySimulationStore(db),
            clock=SystemClock(),
        )
    )


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
