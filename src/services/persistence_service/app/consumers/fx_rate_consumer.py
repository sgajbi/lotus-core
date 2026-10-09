# src/services/persistence_service/app/consumers/fx_rate_consumer.py
from hashlib import sha256
from typing import Any, cast

from portfolio_common.config import (
    KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS,
    KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS,
    KAFKA_FX_RATES_PERSISTED_TOPIC,
)
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.domain.eventing import currency_pair_partition_key
from portfolio_common.domain.transaction import TransactionPayloadIdentity
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import FxRateEvent, FxRatePersistedEvent
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.fx_source_events import FxSourceCutPersistedEvent, FxSourceCutReceivedEvent
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.fx_rate_repository import FxRateRepository
from ..repositories.fx_source_repository import (
    FxSourcePredecessorPending,
    FxSourceRepository,
    RetainedFxCutResult,
)
from .base_consumer import GenericPersistenceConsumer
from .fx_source_cut import FxSourceCutRetryable, PreparedFxSourceCut, prepare_fx_source_cut


class FxSourcePredecessorRetryable(FxSourceCutRetryable):
    """Owning admitted dependency reason; never a blanket source-conflict retry."""

    def __init__(self, reason: str, *, attestation_sha256: str) -> None:
        super().__init__(
            reason, attestation_sha256=attestation_sha256, authorization_stage="admitted"
        )


class FxRateConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently.
    """

    def __init__(self, *args, **kwargs) -> None:
        # The shared zero budgets request restart, not eventual dependency DLQ.
        # Bound this owning consumer through the existing recovery mechanism;
        # explicit tighter limits remain tighter and no generic defaults change.
        for name, configured, ceiling in (
            ("retryable_failure_max_attempts", KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS, 8),
            (
                "retryable_failure_max_elapsed_seconds",
                KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS,
                60,
            ),
        ):
            supplied = kwargs.get(name, configured)
            if supplied is None:
                supplied = configured
            if isinstance(supplied, int) and not isinstance(supplied, bool) and supplied >= 0:
                kwargs[name] = min(supplied, ceiling) if supplied else ceiling
        super().__init__(*args, **kwargs)

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
            try:
                return await FxSourceRepository(db_session).retain_admitted_cut(
                    event.verified.admission, attestation_sha256=event.verified.attestation_sha256
                )
            except FxSourcePredecessorPending as error:
                # Propagate through the owning transaction so its inbox claim and
                # every cut/revision/outbox write roll back before bounded retry.
                raise FxSourcePredecessorRetryable(
                    str(error), attestation_sha256=event.verified.attestation_sha256
                ) from error
        if not isinstance(event, FxRateEvent):
            raise TypeError("FX_SOURCE_EVENT_CONTRACT_INVALID")
        return await FxRateRepository(db_session).upsert_fx_rate(event)

    def _build_dlq_payload(self, msg, error: Exception, **kwargs) -> dict[str, object]:
        payload = cast(dict[str, object], super()._build_dlq_payload(msg, error, **kwargs))
        if isinstance(error, FxSourceCutRetryable):
            # Keep shared authorization redaction. Bind the exact original bytes
            # for operator reconciliation without inventing replay permission.
            payload["original_payload_sha256"] = sha256(msg.value()).hexdigest()
            payload["authorization_stage"] = error.authorization_stage
            # The chained database exception may contain SQL/parameters. Only
            # this bounded owning reason belongs in durable support evidence.
            payload["error_traceback"] = f"{type(error).__name__}: {error}"
            if error.attestation_sha256 is not None:
                payload["attestation_sha256"] = error.attestation_sha256
        return payload

    def database_retry_error(
        self, error: DBAPIError, event: BaseModel | None
    ) -> RetryableConsumerError:
        if isinstance(event, PreparedFxSourceCut):
            return FxSourceCutRetryable(
                "FX_SOURCE_DATABASE_RETRY",
                attestation_sha256=event.verified.attestation_sha256,
                authorization_stage="admitted",
            )
        if isinstance(event, FxSourceCutReceivedEvent):
            return FxSourceCutRetryable("FX_SOURCE_DATABASE_RETRY")
        return super().database_retry_error(error, event)

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
