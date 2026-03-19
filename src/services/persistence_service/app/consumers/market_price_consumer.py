# src/services/persistence_service/app/consumers/market_price_consumer.py
from typing import Any, Dict, Optional

from portfolio_common.config import KAFKA_MARKET_PRICES_PERSISTED_TOPIC
from portfolio_common.events import MarketPriceEvent, MarketPricePersistedEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.market_price_repository import MarketPriceRepository
from .base_consumer import GenericPersistenceConsumer


class MarketPriceConsumer(GenericPersistenceConsumer):
    """
    Validates and persists market price events, then publishes a completion event.
    """

    @property
    def event_model(self):
        return MarketPriceEvent

    @property
    def service_name(self) -> str:
        return "persistence-market-prices"

    async def handle_persistence(self, db_session: AsyncSession, event: MarketPriceEvent) -> Any:
        """Persists the market price and returns the persisted object."""
        repo = MarketPriceRepository(db_session)
        persisted_price = await repo.create_market_price(event)
        return persisted_price

    def get_outbox_event(self, persisted_object: Any) -> Optional[Dict[str, Any]]:
        """Creates the MarketPricePersisted event to be sent via the outbox."""
        outbound_event = MarketPricePersistedEvent.model_validate(
            persisted_object, from_attributes=True
        )
        return {
            "aggregate_type": "MarketPrice",
            "aggregate_id": persisted_object.security_id,
            "event_type": "MarketPricePersisted",
            "topic": KAFKA_MARKET_PRICES_PERSISTED_TOPIC,
            "payload": outbound_event.model_dump(mode="json"),
        }
