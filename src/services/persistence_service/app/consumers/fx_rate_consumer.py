# src/services/persistence_service/app/consumers/fx_rate_consumer.py
from typing import Any

from portfolio_common.config import KAFKA_FX_RATES_PERSISTED_TOPIC
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.domain.eventing import currency_pair_partition_key
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import FxRateEvent, FxRatePersistedEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.fx_rate_repository import FxRateRepository
from .base_consumer import GenericPersistenceConsumer


class FxRateConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently.
    """

    @property
    def event_model(self) -> type[FxRateEvent]:
        return FxRateEvent

    @property
    def service_name(self) -> str:
        return "persistence-fx-rates"

    async def handle_persistence(self, db_session: AsyncSession, event: FxRateEvent) -> DBFxRate:
        """Persists the FX rate event using its specific repository."""
        repo = FxRateRepository(db_session)
        return await repo.upsert_fx_rate(event)

    def get_outbox_event(self, persisted_object: Any) -> dict[str, Any] | None:
        """Build the source-owned persisted FX observation event."""
        observation = FxRateEvent.model_validate(persisted_object, from_attributes=True)
        outbound_event = FxRatePersistedEvent.from_observation(observation)
        pair = f"{outbound_event.from_currency}-{outbound_event.to_currency}"
        return {
            "aggregate_type": "FxRate",
            "aggregate_id": pair,
            "partition_key": currency_pair_partition_key(
                outbound_event.from_currency,
                outbound_event.to_currency,
            ),
            "event_type": "FxRatePersisted",
            "topic": KAFKA_FX_RATES_PERSISTED_TOPIC,
            "payload": outbox_event_payload(outbound_event),
        }
