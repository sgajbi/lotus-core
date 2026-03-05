# src/services/persistence_service/app/consumers/business_date_consumer.py
from portfolio_common.events import BusinessDateEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.business_date_repository import BusinessDateRepository
from .base_consumer import GenericPersistenceConsumer


class BusinessDateConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists business date events idempotently.
    This consumer does not produce any outbound events.
    """
    @property
    def event_model(self):
        return BusinessDateEvent

    @property
    def service_name(self) -> str:
        return "persistence-business-dates"

    async def handle_persistence(self, db_session: AsyncSession, event: BusinessDateEvent):
        """Persists the business date event using its specific repository."""
        repo = BusinessDateRepository(db_session)
        await repo.upsert_business_date(event)
        # This consumer does not create an outbox event, so we return None.
        return None