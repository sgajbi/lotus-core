# src/services/persistence_service/app/consumers/base_consumer.py
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from confluent_kafka import Message
from portfolio_common.db import get_async_db_session
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

logger = logging.getLogger(__name__)

class GenericPersistenceConsumer(BaseConsumer, ABC):
    """
    An abstract base class for persistence consumers that handles common boilerplate:
    - JSON Deserialization and Pydantic Validation
    - Idempotency checks
    - Database transaction and session management
    - Error handling, retries, and DLQ publishing
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

    @abstractmethod
    async def handle_persistence(self, db_session, event: BaseModel) -> Any:
        """
        The core persistence logic to be implemented by subclasses.
        This method is responsible for calling the appropriate repository method.
        It should return the persisted database object if an outbox event is needed.
        """
        pass

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
        - For validation/poison-pill errors, sends to DLQ.
        - For unexpected errors, raises them to be handled by the BaseConsumer.
        """
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = self.event_model.model_validate(event_data)
            
            idempotency_key = getattr(event, 'transaction_id', event_id)

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)

                    if await idempotency_repo.is_event_processed(idempotency_key, self.service_name):
                        logger.warning(f"Event {idempotency_key} already processed. Skipping.")
                        return

                    persisted_object = await self.handle_persistence(db, event)
                    
                    outbox_details = self.get_outbox_event(persisted_object)
                    if outbox_details:
                        outbox_repo = OutboxRepository(db)
                        await outbox_repo.create_outbox_event(correlation_id=correlation_id, **outbox_details)

                    await idempotency_repo.mark_event_processed(
                        event_id=idempotency_key,
                        portfolio_id=getattr(event, 'portfolio_id', 'N/A'),
                        service_name=self.service_name,
                        correlation_id=correlation_id
                    )

        except (json.JSONDecodeError, ValidationError) as e:
            # This is a non-retryable "poison pill" message. Send to DLQ.
            logger.error("Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
            # IMPORTANT: Re-raise a generic exception to ensure the base consumer commits the offset.
            raise ValueError("Poison pill message detected") 
        except (DBAPIError, IntegrityError, OperationalError) as e:
            # This is a transient DB error. Signal the base consumer to retry.
            logger.warning(f"DB error for {self.service_name}. Raising RetryableConsumerError.", exc_info=False)
            raise RetryableConsumerError(f"Database error: {e}") from e