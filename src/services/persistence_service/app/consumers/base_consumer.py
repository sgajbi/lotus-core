# src/services/persistence_service/app/consumers/base_consumer.py
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from confluent_kafka import Message
from portfolio_common.consumer_error_evidence import validation_error_diagnostics
from portfolio_common.db import get_async_db_session
from portfolio_common.domain.transaction import TransactionPayloadIdentity
from portfolio_common.exceptions import RetryableConsumerError, TransactionSemanticConflictError
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import log_operation_event
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from ..adapters.persistence_event_adapter import (
    decode_persistence_message_payload,
    validate_persistence_event_payload,
)

logger = logging.getLogger(__name__)


class GenericPersistenceConsumer(BaseConsumer, ABC):
    """
    An abstract base class for persistence consumers that handles common boilerplate:
    - JSON Deserialization and Pydantic Validation
    - Idempotency checks
    - Database transaction and session management
    - Error classification for the shared consumer recovery boundary
    - Optional outbox event creation on success
    """

    @property
    @abstractmethod
    def event_model(self) -> Type[BaseModel]:
        """The Pydantic event model for validating the incoming message."""
        pass

    @property
    @abstractmethod
    def service_name(self) -> str:
        """The unique name of the service for idempotency tracking."""
        pass

    @property
    def tenant_scoped_idempotency(self) -> bool:
        """Whether this consumer's processed-event identity includes tenant ownership."""

        return False

    def resolve_event_model(self, payload: dict[str, Any]) -> Type[BaseModel]:
        """Select an explicit typed variant when one owning topic has multiple contracts."""
        return self.event_model

    def is_event_tenant_scoped(self, event: BaseModel) -> bool:
        return self.tenant_scoped_idempotency

    @abstractmethod
    async def handle_persistence(self, db_session, event: BaseModel) -> Any:
        """
        The core persistence logic to be implemented by subclasses.
        This method is responsible for calling the appropriate repository method.
        It should return the persisted database object if an outbox event is needed.
        """
        pass

    async def prepare_event(self, db_session, event: BaseModel) -> BaseModel:
        """Resolve consumer-specific authority before the idempotency claim."""

        return event

    def semantic_idempotency_identity(
        self,
        event: BaseModel,
    ) -> TransactionPayloadIdentity | None:
        """Return a semantic claim for consumers with durable payload identity."""

        return None

    async def is_compatible_semantic_conflict(
        self,
        db_session,
        event: BaseModel,
        semantic_identity: TransactionPayloadIdentity,
    ) -> bool:
        """Return true only for a consumer-owned rolling-version compatibility rule."""

        return False

    def get_outbox_event(self, persisted_object: Any) -> Optional[Dict[str, Any]]:
        """
        Subclasses can override this to create an outbox event upon successful persistence.
        Return a dictionary with kwargs for OutboxRepository.create_outbox_event.
        """
        return None

    async def process_message(self, msg: Message):
        """
        Processes a single message.
        - For transient DB errors, raises RetryableConsumerError to trigger Kafka redelivery.
        - For validation/poison-pill errors, raises to the shared DLQ boundary.
        - For unexpected errors, raises them to be handled by the BaseConsumer.
        """
        event = None
        message_correlation_id: str | None = None

        try:
            decoded_payload = decode_persistence_message_payload(msg)
            with self._message_correlation_context(
                msg,
                fallback_correlation_id=decoded_payload.fallback_correlation_id,
            ) as correlation_id:
                message_correlation_id = correlation_id
                envelope = validate_persistence_event_payload(
                    decoded_payload, self.resolve_event_model(decoded_payload.data)
                )
                event = envelope.event

                async for db in get_async_db_session():
                    async with db.begin():
                        event = await self.prepare_event(db, event)
                        idempotency_repo = IdempotencyRepository(db)
                        tenant_scope: dict[str, str | None] = {}
                        if self.is_event_tenant_scoped(event):
                            tenant_scope["tenant_id"] = getattr(event, "tenant_id", None)
                        semantic_identity = self.semantic_idempotency_identity(event)
                        if semantic_identity is None:
                            claimed = await idempotency_repo.claim_event_processing(
                                envelope.idempotency_key,
                                envelope.portfolio_id,
                                self.service_name,
                                correlation_id,
                                **tenant_scope,
                            )
                            duplicate = not claimed
                        else:
                            outcome = await idempotency_repo.claim_semantic_event_processing(
                                event_id=envelope.idempotency_key,
                                portfolio_id=envelope.portfolio_id,
                                service_name=self.service_name,
                                semantic_key=semantic_identity.semantic_key,
                                payload_fingerprint=semantic_identity.payload_fingerprint,
                                correlation_id=correlation_id,
                                **tenant_scope,
                            )
                            if outcome is SemanticEventClaimOutcome.SEMANTIC_CONFLICT:
                                if await self.is_compatible_semantic_conflict(
                                    db,
                                    event,
                                    semantic_identity,
                                ):
                                    return
                                existing_fingerprint = (
                                    await idempotency_repo.resolve_semantic_payload_fingerprint(
                                        event_id=envelope.idempotency_key,
                                        service_name=self.service_name,
                                        semantic_key=semantic_identity.semantic_key,
                                        **tenant_scope,
                                    )
                                )
                                raise TransactionSemanticConflictError(
                                    semantic_key=semantic_identity.semantic_key,
                                    existing_payload_fingerprint=existing_fingerprint,
                                    incoming_payload_fingerprint=(
                                        semantic_identity.payload_fingerprint
                                    ),
                                )
                            duplicate = outcome in {
                                SemanticEventClaimOutcome.PHYSICAL_DUPLICATE,
                                SemanticEventClaimOutcome.SEMANTIC_DUPLICATE,
                            }
                        if duplicate:
                            logger.warning(
                                f"Event {envelope.idempotency_key} already processed. Skipping."
                            )
                            return

                        persisted_object = await self.handle_persistence(db, event)

                        outbox_details = self.get_outbox_event(persisted_object)
                        if outbox_details:
                            outbox_repo = OutboxRepository(db)
                            await outbox_repo.create_outbox_event(
                                correlation_id=correlation_id, **outbox_details
                            )

        except json.JSONDecodeError as error:
            with self._message_correlation_context(msg) as correlation_id:
                log_operation_event(
                    logger,
                    logging.ERROR,
                    "Message validation failed.",
                    event_name="persistence.message.validation",
                    operation="persistence_consume",
                    status="rejected",
                    reason_code="json_decode_failed",
                    message_correlation_id=correlation_id,
                    error_type=type(error).__name__,
                    json_line=error.lineno,
                    json_column=error.colno,
                    json_position=error.pos,
                )
            raise
        except ValidationError as error:
            log_operation_event(
                logger,
                logging.ERROR,
                "Message validation failed.",
                event_name="persistence.message.validation",
                operation="persistence_consume",
                status="rejected",
                reason_code="schema_validation_failed",
                message_correlation_id=message_correlation_id,
                error_type=type(error).__name__,
                **validation_error_diagnostics(error),
            )
            raise
        except (DBAPIError, IntegrityError, OperationalError) as e:
            # This is a transient DB error. Signal the base consumer to retry.
            logger.warning(
                f"DB error for {self.service_name}. Raising RetryableConsumerError.", exc_info=False
            )
            raise RetryableConsumerError(f"Database error: {e}") from e
