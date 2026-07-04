# services/persistence_service/app/consumers/transaction_consumer.py
import logging
from typing import Any, Dict, Optional

from portfolio_common.config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from portfolio_common.event_mapping import outbox_event_payload
from portfolio_common.events import TransactionEvent
from portfolio_common.logging_utils import log_operation_event
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed

from ..policies.transaction_cash_account_policy import (
    decide_transaction_cash_account_reference,
)
from ..policies.transaction_instrument_policy import (
    decide_transaction_instrument_reference,
)
from ..repositories.transaction_db_repo import TransactionDBRepository
from .base_consumer import GenericPersistenceConsumer

logger = logging.getLogger(__name__)


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

        instrument_exists = await repo.check_instrument_exists(event.security_id)
        instrument_decision = decide_transaction_instrument_reference(
            security_id=event.security_id,
            instrument_exists=instrument_exists,
        )
        if instrument_decision.reason_code is not None:
            log_operation_event(
                logger,
                logging.WARNING,
                "Transaction raw landing has unresolved instrument reference.",
                event_name="persistence.transaction.instrument_reference",
                operation="transaction_persistence",
                status=instrument_decision.status,
                reason_code=instrument_decision.reason_code,
                policy_id=instrument_decision.policy_id,
                downstream_lifecycle_blocked=instrument_decision.downstream_lifecycle_blocked,
            )

        cash_account_exists = None
        if (event.settlement_cash_account_id or "").strip():
            cash_account_exists = await repo.check_active_cash_account_exists(
                portfolio_id=event.portfolio_id,
                cash_account_id=event.settlement_cash_account_id or "",
                cash_security_id=event.settlement_cash_instrument_id,
                as_of_date=(event.settlement_date or event.transaction_date).date(),
            )
        cash_account_decision = decide_transaction_cash_account_reference(
            settlement_cash_account_id=event.settlement_cash_account_id,
            cash_account_exists=cash_account_exists,
        )
        if cash_account_decision.reason_code is not None:
            log_operation_event(
                logger,
                logging.WARNING,
                "Transaction raw landing has unresolved settlement cash-account reference.",
                event_name="persistence.transaction.cash_account_reference",
                operation="transaction_persistence",
                status=cash_account_decision.status,
                reason_code=cash_account_decision.reason_code,
                policy_id=cash_account_decision.policy_id,
                downstream_lifecycle_blocked=(cash_account_decision.downstream_lifecycle_blocked),
            )

        await repo.create_or_update_transaction(event)
        return event

    def get_outbox_event(self, persisted_object: TransactionEvent) -> Optional[Dict[str, Any]]:
        """Creates the completion event to be sent via the outbox."""
        return {
            "aggregate_type": "RawTransaction",
            "aggregate_id": str(persisted_object.portfolio_id),
            "event_type": "RawTransactionPersisted",
            "topic": KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            "payload": outbox_event_payload(persisted_object),
        }
