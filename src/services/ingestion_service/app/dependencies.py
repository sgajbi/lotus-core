from fastapi import Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from portfolio_common.event_publisher import EventPublisher, get_kafka_event_publisher
from sqlalchemy.ext.asyncio import AsyncSession

from .adapter_mode import (
    AdapterModeDisabledError,
    ensure_portfolio_bundle_adapter_enabled,
    ensure_upload_adapter_enabled,
)
from .repositories.business_calendar_repository import BusinessCalendarRepository
from .services.business_date_ingestion_commands import BusinessDateIngestionCommandHandler
from .services.business_date_ingestion_policy import BusinessDateIngestionPolicy
from .services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from .services.ingestion_service import IngestionService
from .services.reference_data_ingestion_service import ReferenceDataIngestionService


def adapter_mode_disabled_http_error(exc: AdapterModeDisabledError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_410_GONE, detail=exc.detail)


def require_portfolio_bundle_adapter_enabled() -> None:
    try:
        ensure_portfolio_bundle_adapter_enabled()
    except AdapterModeDisabledError as exc:
        raise adapter_mode_disabled_http_error(exc) from exc


def require_upload_adapter_enabled() -> None:
    try:
        ensure_upload_adapter_enabled()
    except AdapterModeDisabledError as exc:
        raise adapter_mode_disabled_http_error(exc) from exc


def get_ingestion_service(
    event_publisher: EventPublisher = Depends(get_kafka_event_publisher),
) -> IngestionService:
    return IngestionService(event_publisher)


def get_reference_data_ingestion_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReferenceDataIngestionService:
    return ReferenceDataIngestionService(db)


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


def get_business_date_ingestion_command_handler(
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    business_date_policy: BusinessDateIngestionPolicy = Depends(get_business_date_ingestion_policy),
) -> BusinessDateIngestionCommandHandler:
    return BusinessDateIngestionCommandHandler(
        ingestion_service=ingestion_service,
        ingestion_job_service=ingestion_job_service,
        business_date_policy=business_date_policy,
    )
