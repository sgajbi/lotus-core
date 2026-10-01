"""Resolve database DLQ evidence ownership from the durable ingestion job."""

from sqlalchemy import select

from .database_models import IngestionJob
from .db import get_async_db_session


class ConsumerDlqTenantAttributionError(RuntimeError):
    """Broker DLQ evidence exists but cannot be attributed for database persistence."""


async def resolve_consumer_dlq_tenant_id(ingestion_job_id: str | None) -> str:
    if ingestion_job_id is None:
        raise ConsumerDlqTenantAttributionError(
            "Consumer DLQ event has no durable ingestion job owner."
        )
    async for db in get_async_db_session():
        result = await db.execute(
            select(IngestionJob.tenant_id).where(IngestionJob.job_id == ingestion_job_id)
        )
        tenant_id = result.scalar_one_or_none()
        if tenant_id is not None:
            return str(tenant_id)
        raise ConsumerDlqTenantAttributionError(
            "Consumer DLQ event references an unknown ingestion job owner."
        )
    raise RuntimeError("Database session unavailable while resolving DLQ ingestion owner.")
