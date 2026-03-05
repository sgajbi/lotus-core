# services/persistence_service/app/consumers/transaction_consumer.py
from typing import Any, Dict, Optional

from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed

from ..repositories.transaction_db_repo import TransactionDBRepository
from .base_consumer import GenericPersistenceConsumer


class PortfolioNotFoundError(Exception):
    """Custom exception to signal a retryable condition."""

    pass


class TransactionPersistenceConsumer(GenericPersistenceConsumer):
    """
    Consumes, validates, and persists raw transaction events.
    """

    @property
    def event_model(self):
        return TransactionEvent

    @property
    def service_name(self) -> str:
        return "persistence-transactions"

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_delay(10),
        retry=retry_if_exception_type(PortfolioNotFoundError),
        reraise=True,
    )
    async def handle_persistence(self, db_session: AsyncSession, event: TransactionEvent) -> Any:
        """
        Checks for portfolio existence and persists the transaction.
        Returns the event for outbox creation.
        """
        repo = TransactionDBRepository(db_session)

        portfolio_exists = await repo.check_portfolio_exists(event.portfolio_id)
        if not portfolio_exists:
            raise PortfolioNotFoundError(
                "Portfolio "
                f"{event.portfolio_id} not found for transaction "
                f"{event.transaction_id}. Retrying..."
            )

        await repo.create_or_update_transaction(event)
        return event

    def get_outbox_event(self, persisted_object: TransactionEvent) -> Optional[Dict[str, Any]]:
        """Creates the completion event to be sent via the outbox."""
        return {
            "aggregate_type": "RawTransaction",
            "aggregate_id": str(persisted_object.portfolio_id),
            "event_type": "RawTransactionPersisted",
            "topic": KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
            "payload": persisted_object.model_dump(mode="json"),
        }
