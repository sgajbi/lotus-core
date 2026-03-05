# src/services/persistence_service/app/consumers/instrument_consumer.py
from portfolio_common.events import InstrumentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.instrument_repository import InstrumentRepository
from .base_consumer import GenericPersistenceConsumer


class InstrumentConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists instrument events using the generic persistence consumer.
    """
    @property
    def event_model(self):
        return InstrumentEvent

    @property
    def service_name(self) -> str:
        return "persistence-instruments"

    async def handle_persistence(self, db_session: AsyncSession, event: InstrumentEvent):
        """Persists the instrument event using its specific repository."""
        repo = InstrumentRepository(db_session)
        await repo.create_or_update_instrument(event)
        # This consumer does not create an outbox event, so we return None.
        return None