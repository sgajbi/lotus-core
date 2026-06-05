# src/libs/portfolio-common/portfolio_common/reprocessing_repository.py
import logging
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import KAFKA_TRANSACTIONS_PERSISTED_TOPIC
from .database_models import Transaction as DBTransaction
from .events import TransactionEvent
from .kafka_utils import KafkaProducer
from .logging_utils import correlation_id_var, normalize_lineage_value

logger = logging.getLogger(__name__)


class ReprocessingReplayError(RuntimeError):
    def __init__(
        self,
        message: str,
        failed_transaction_ids: list[str],
        published_record_count: int = 0,
    ):
        super().__init__(message)
        self.failed_transaction_ids = failed_transaction_ids
        self.published_record_count = published_record_count


class ReprocessingRepository:
    """
    Handles the logic for reprocessing financial data by republishing events.
    """

    def __init__(self, db: AsyncSession, kafka_producer: KafkaProducer):
        self.db = db
        self.kafka_producer = kafka_producer

    @staticmethod
    def _raise_partial_replay_error(
        *,
        failed_transaction_id: str,
        ordered_transaction_ids: list[str],
        failure_index: int,
    ) -> None:
        unpublished_transaction_ids = ordered_transaction_ids[failure_index:]
        published_record_count = failure_index
        earlier_records = (
            f"{published_record_count} earlier transaction(s) were already republished"
            if published_record_count
            else "no earlier transactions were republished"
        )
        remaining_ids = ", ".join(unpublished_transaction_ids)
        raise ReprocessingReplayError(
            (
                f"Failed to republish transaction '{failed_transaction_id}' after "
                f"{earlier_records}. Remaining transaction ids: {remaining_ids}."
            ),
            failed_transaction_ids=unpublished_transaction_ids,
            published_record_count=published_record_count,
        )

    @staticmethod
    def _raise_flush_timeout_error(*, ordered_transaction_ids: list[str]) -> None:
        remaining_ids = ", ".join(ordered_transaction_ids)
        raise ReprocessingReplayError(
            (
                "Delivery confirmation timed out while republishing transactions. "
                f"Affected transaction ids: {remaining_ids}."
            ),
            failed_transaction_ids=ordered_transaction_ids,
            published_record_count=0,
        )

    async def reprocess_transactions_by_ids(self, transaction_ids: list[str]) -> int:
        """
        Fetches a list of transactions by their IDs and republishes their
        'transactions.persisted' event to trigger a full recalculation.

        Args:
            transaction_ids: A list of transaction_id strings to reprocess.

        Returns:
            The number of transactions that were found and republished.
        """
        ordered_unique_ids = _ordered_unique_transaction_ids(transaction_ids)
        if not ordered_unique_ids:
            return 0

        logger.info(f"Beginning reprocessing for {len(ordered_unique_ids)} transaction(s).")

        transactions_to_replay = await self._fetch_transactions_to_replay(ordered_unique_ids)
        if not transactions_to_replay:
            _log_no_matching_transactions(ordered_unique_ids)
            return 0

        headers = _correlation_headers()
        replayed_transaction_ids = [txn.transaction_id for txn in transactions_to_replay]
        self._publish_transactions_to_replay(
            transactions_to_replay=transactions_to_replay,
            replayed_transaction_ids=replayed_transaction_ids,
            headers=headers,
        )
        self._flush_replayed_transactions(replayed_transaction_ids)
        logger.info(f"Successfully republished {len(transactions_to_replay)} transaction event(s).")

        return len(transactions_to_replay)

    async def _fetch_transactions_to_replay(
        self, ordered_transaction_ids: list[str]
    ) -> list[DBTransaction]:
        result = await self.db.execute(_transactions_to_replay_stmt(ordered_transaction_ids))
        return result.scalars().all()

    def _publish_transactions_to_replay(
        self,
        *,
        transactions_to_replay: list[DBTransaction],
        replayed_transaction_ids: list[str],
        headers: list[tuple[str, bytes]],
    ) -> None:
        for idx, txn in enumerate(transactions_to_replay):
            try:
                self._publish_transaction_to_replay(txn=txn, headers=headers)
            except Exception as exc:
                self._raise_partial_replay_error_from_publish_failure(
                    failed_transaction_id=txn.transaction_id,
                    ordered_transaction_ids=replayed_transaction_ids,
                    failure_index=idx,
                    cause=exc,
                )

    def _publish_transaction_to_replay(
        self,
        *,
        txn: DBTransaction,
        headers: list[tuple[str, bytes]],
    ) -> None:
        event_to_publish = TransactionEvent.model_validate(txn)
        logger.info(
            "Republishing event for transaction.",
            extra={
                "transaction_id": txn.transaction_id,
                "topic": KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            },
        )
        self.kafka_producer.publish_message(
            topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
            key=txn.portfolio_id,
            value=event_to_publish.model_dump(mode="json"),
            headers=headers,
        )

    def _raise_partial_replay_error_from_publish_failure(
        self,
        *,
        failed_transaction_id: str,
        ordered_transaction_ids: list[str],
        failure_index: int,
        cause: Exception,
    ) -> None:
        try:
            self._raise_partial_replay_error(
                failed_transaction_id=failed_transaction_id,
                ordered_transaction_ids=ordered_transaction_ids,
                failure_index=failure_index,
            )
        except ReprocessingReplayError as replay_exc:
            raise replay_exc from cause

    def _flush_replayed_transactions(self, replayed_transaction_ids: list[str]) -> None:
        undelivered_count = self.kafka_producer.flush()
        if undelivered_count:
            self._raise_flush_timeout_error(ordered_transaction_ids=replayed_transaction_ids)


def _ordered_unique_transaction_ids(transaction_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(transaction_ids))


def _transactions_to_replay_stmt(ordered_transaction_ids: list[str]) -> Any:
    ordering = case(
        {transaction_id: index for index, transaction_id in enumerate(ordered_transaction_ids)},
        value=DBTransaction.transaction_id,
    )
    return (
        select(DBTransaction)
        .where(DBTransaction.transaction_id.in_(ordered_transaction_ids))
        .order_by(ordering)
    )


def _log_no_matching_transactions(ordered_transaction_ids: list[str]) -> None:
    logger.warning(
        "No matching transactions found in the database for the given IDs.",
        extra={"transaction_ids": ordered_transaction_ids},
    )


def _correlation_headers() -> list[tuple[str, bytes]]:
    correlation_id = normalize_lineage_value(correlation_id_var.get())
    if not correlation_id:
        return []
    return [("correlation_id", correlation_id.encode("utf-8"))]
