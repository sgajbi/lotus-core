# src/services/persistence_service/app/consumers/fx_rate_consumer.py
from typing import Any, cast

from portfolio_common.config import KAFKA_FX_RATES_PERSISTED_TOPIC
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.domain.eventing import currency_pair_partition_key
from portfolio_common.domain.transaction import TransactionPayloadIdentity
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import FxRateEvent, FxRatePersistedEvent
from portfolio_common.fx_source_events import FxSourceCutPersistedEvent, FxSourceCutReceivedEvent
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.fx_rate_repository import FxRateRepository
from ..repositories.fx_source_repository import FxSourceRepository, RetainedFxCutResult
from .base_consumer import GenericPersistenceConsumer
from .fx_source_cut import PreparedFxSourceCut, prepare_fx_source_cut


class FxRateConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently.
    """

    @property
    def event_model(self) -> type[FxRateEvent]:
        return cast(type[FxRateEvent], FxRateEvent)

    @property
    def service_name(self) -> str:
        return "persistence-fx-rates"

    def resolve_event_model(self, payload: dict[str, Any]) -> type[BaseModel]:
        if payload.get("event_type") == "FxSourceCutReceived":
            return FxSourceCutReceivedEvent
        return cast(type[BaseModel], FxRateEvent)

    def is_event_tenant_scoped(self, event: BaseModel) -> bool:
        return isinstance(event, PreparedFxSourceCut)

    async def prepare_event(self, db_session: AsyncSession, event: BaseModel) -> BaseModel:
        if isinstance(event, FxSourceCutReceivedEvent):
            return await prepare_fx_source_cut(db_session, event)
        return event

    def semantic_idempotency_identity(self, event: BaseModel) -> TransactionPayloadIdentity | None:
        if not isinstance(event, PreparedFxSourceCut):
            return None
        cut = event.verified.admission.cut
        return TransactionPayloadIdentity(cut.cut_id, cut.content_hash, cut.content_hash)

    async def handle_persistence(
        self, db_session: AsyncSession, event: BaseModel
    ) -> DBFxRate | RetainedFxCutResult:
        """Persists the FX rate event using its specific repository."""
        if isinstance(event, PreparedFxSourceCut):
            return await FxSourceRepository(db_session).retain_admitted_cut(
                event.verified.admission, attestation_sha256=event.verified.attestation_sha256
            )
        if not isinstance(event, FxRateEvent):
            raise TypeError("FX_SOURCE_EVENT_CONTRACT_INVALID")
        return await FxRateRepository(db_session).upsert_fx_rate(event)

    def get_outbox_event(self, persisted_object: Any) -> dict[str, Any] | None:
        """Build the source-owned persisted FX observation event."""
        if isinstance(persisted_object, RetainedFxCutResult):
            if persisted_object.replayed:
                return None
            row = persisted_object.row
            notification = FxSourceCutPersistedEvent(
                tenant_id=row.tenant_id,
                provider_id=row.provider_id,
                source_id=row.source_id,
                cut_id=row.cut_id,
                content_hash=row.content_hash,
                member_count=row.member_count,
                members=row.members,
                accepted_at=row.accepted_at,
                source_observed_cutoff=row.source_observed_cutoff,
            )
            return {
                "aggregate_type": "FxSourceCut",
                "aggregate_id": row.cut_id,
                "partition_key": row.cut_id,
                "event_type": "FxSourceCutPersisted",
                "topic": KAFKA_FX_RATES_PERSISTED_TOPIC,
                "payload": outbox_event_payload(notification),
            }
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
