# src/services/persistence_service/app/consumers/fx_rate_consumer.py
from portfolio_common.events import FxRateEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.fx_rate_repository import FxRateRepository
from .base_consumer import GenericPersistenceConsumer


class FxRateConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently.
    """
    @property
    def event_model(self):
        return FxRateEvent

    @property
    def service_name(self) -> str:
        return "persistence-fx-rates"

    async def handle_persistence(self, db_session: AsyncSession, event: FxRateEvent):
        """Persists the FX rate event using its specific repository."""
        repo = FxRateRepository(db_session)
        await repo.upsert_fx_rate(event)
        return None