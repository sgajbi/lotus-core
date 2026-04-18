# libs/portfolio-common/portfolio_common/idempotency_repository.py
import logging
from typing import Optional

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ProcessedEvent
from .logging_utils import normalize_lineage_value

logger = logging.getLogger(__name__)


class IdempotencyRepository:
    """
    Handles all database interactions for ensuring idempotency via the
    processed_events table. Now supports AsyncSession.
    """

    def __init__(self, db: AsyncSession):
        """
        Initializes the repository with an asynchronous database session.
        Args:
            db: The SQLAlchemy AsyncSession to use for database operations.
        """
        self.db = db

    async def is_event_processed(self, event_id: str, service_name: str) -> bool:
        """
        Asynchronously checks if an event has already been processed by a specific service.
        Args:
            event_id: The unique identifier of the event.
            service_name: The name of the service processing the event.

        Returns:
            True if the event has been processed, False otherwise.
        """
        stmt = select(
            exists().where(
                ProcessedEvent.event_id == event_id, ProcessedEvent.service_name == service_name
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar()

    async def mark_event_processed(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Asynchronously records an event as processed using a schema-backed upsert.

        Returns True when the event was newly recorded, False when the uniqueness
        fence already existed.
        Args:
            event_id: The unique identifier of the event.
            portfolio_id: The portfolio ID associated with the event.
            service_name: The name of the service that processed the event.
            correlation_id: The correlation ID for tracing the event flow.
        """
        correlation_id = normalize_lineage_value(correlation_id)
        stmt = (
            pg_insert(ProcessedEvent)
            .values(
                event_id=event_id,
                portfolio_id=portfolio_id,
                service_name=service_name,
                correlation_id=correlation_id,
            )
            .on_conflict_do_nothing(
                index_elements=["event_id", "service_name"],
            )
            .returning(ProcessedEvent.id)
        )
        inserted_id = (await self.db.execute(stmt)).scalar_one_or_none()
        claimed = inserted_id is not None
        logger.debug(
            "Processed-event fence %s for service %s",
            "created" if claimed else "already existed",
            service_name,
            extra={
                "event_id": event_id,
                "service_name": service_name,
                "correlation_id": correlation_id,
            },
        )
        return claimed

    async def claim_event_processing(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Atomically claims an event-processing fence at the start of a transaction.

        Callers should use this before mutating durable state. If the surrounding
        transaction rolls back, the claim rolls back with it.
        """
        return await self.mark_event_processed(
            event_id=event_id,
            portfolio_id=portfolio_id,
            service_name=service_name,
            correlation_id=correlation_id,
        )
