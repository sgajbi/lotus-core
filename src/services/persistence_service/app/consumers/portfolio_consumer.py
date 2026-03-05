# src/services/persistence_service/app/consumers/portfolio_consumer.py
from portfolio_common.events import PortfolioEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.portfolio_repository import PortfolioRepository
from .base_consumer import GenericPersistenceConsumer


class PortfolioConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists portfolio events idempotently.
    """
    @property
    def event_model(self):
        return PortfolioEvent

    @property
    def service_name(self) -> str:
        return "persistence-portfolios"

    async def handle_persistence(self, db_session: AsyncSession, event: PortfolioEvent):
        """Persists the portfolio event using its specific repository."""
        repo = PortfolioRepository(db_session)
        await repo.create_or_update_portfolio(event)
        return None