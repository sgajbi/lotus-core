# src/libs/portfolio-common/portfolio_common/reprocessing_repository.py
import logging
from typing import List

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from .database_models import Transaction as DBTransaction
from .events import TransactionEvent
from .kafka_utils import KafkaProducer
from .logging_utils import correlation_id_var, normalize_lineage_value

logger = logging.getLogger(__name__)


class ReprocessingRepository:
    """
    Handles the logic for reprocessing financial data by republishing events.
    """

    def __init__(self, db: AsyncSession, kafka_producer: KafkaProducer):
        self.db = db
        self.kafka_producer = kafka_producer

    async def reprocess_transactions_by_ids(self, transaction_ids: List[str]) -> int:
        """
        Fetches a list of transactions by their IDs and republishes their
        'raw_transactions_completed' event to trigger a full recalculation.

        Args:
            transaction_ids: A list of transaction_id strings to reprocess.

        Returns:
            The number of transactions that were found and republished.
        """
        ordered_unique_ids = list(dict.fromkeys(transaction_ids))

        if not ordered_unique_ids:
            return 0

        logger.info(f"Beginning reprocessing for {len(ordered_unique_ids)} transaction(s).")

        ordering = case(
            {transaction_id: index for index, transaction_id in enumerate(ordered_unique_ids)},
            value=DBTransaction.transaction_id,
        )
        stmt = (
            select(DBTransaction)
            .where(DBTransaction.transaction_id.in_(ordered_unique_ids))
            .order_by(ordering)
        )
        result = await self.db.execute(stmt)
        transactions_to_replay = result.scalars().all()

        if not transactions_to_replay:
            logger.warning(
                "No matching transactions found in the database for the given IDs.",
                extra={"transaction_ids": ordered_unique_ids},
            )
            return 0

        correlation_id = normalize_lineage_value(correlation_id_var.get())
        headers = (
            [("correlation_id", (correlation_id or "").encode("utf-8"))] if correlation_id else []
        )

        for txn in transactions_to_replay:
            # Convert the DB model to the Pydantic event model
            event_to_publish = TransactionEvent.model_validate(txn)

            logger.info(
                "Republishing event for transaction.",
                extra={
                    "transaction_id": txn.transaction_id,
                    "topic": KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                },
            )

            self.kafka_producer.publish_message(
                topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                key=txn.portfolio_id,
                value=event_to_publish.model_dump(mode="json"),
                headers=headers,
            )

        self.kafka_producer.flush()
        logger.info(f"Successfully republished {len(transactions_to_replay)} transaction event(s).")

        return len(transactions_to_replay)
