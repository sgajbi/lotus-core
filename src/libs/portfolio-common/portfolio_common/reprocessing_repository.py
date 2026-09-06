# src/libs/portfolio-common/portfolio_common/reprocessing_repository.py
import logging
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import Portfolio
from .database_models import Transaction as DBTransaction
from .ingestion_lineage import ingestion_job_id_var, normalize_ingestion_job_id
from .kafka_utils import KafkaProducer
from .logging_utils import correlation_id_var, normalize_lineage_value
from .reprocessing_replay import (
    ReplayCorrelationMetadata,
    ReprocessingReplayError,
    TransactionReplayMessage,
    TransactionReplayPublisher,
    TransactionReplayReader,
    TRANSACTION_REPLAY_SOURCE_FIELD_NAMES,
    ordered_unique_transaction_ids,
    plan_transaction_replay,
    publish_transaction_replay_plan,
)

logger = logging.getLogger(__name__)
__all__ = [
    "KafkaTransactionReplayPublisher",
    "ReprocessingReplayError",
    "ReprocessingRepository",
    "SqlAlchemyTransactionReplayReader",
]


class ReprocessingRepository:
    """
    Handles the logic for reprocessing financial data by republishing events.
    """

    def __init__(self, db: AsyncSession, kafka_producer: KafkaProducer):
        self.db: AsyncSession | None = db
        self.kafka_producer: KafkaProducer | None = kafka_producer
        self._reader: TransactionReplayReader = SqlAlchemyTransactionReplayReader(db)
        self._publisher: TransactionReplayPublisher = KafkaTransactionReplayPublisher(
            kafka_producer
        )

    @classmethod
    def from_ports(
        cls,
        *,
        reader: TransactionReplayReader,
        publisher: TransactionReplayPublisher,
    ) -> "ReprocessingRepository":
        repository = cls.__new__(cls)
        repository.db = None
        repository.kafka_producer = None
        repository._reader = reader
        repository._publisher = publisher
        return repository

    async def reprocess_transactions_by_ids(
        self,
        transaction_ids: list[str],
        *,
        correlation_id: str | None = None,
        repair_delivery_id: str | None = None,
    ) -> int:
        ordered_unique_ids = ordered_unique_transaction_ids(transaction_ids)
        if not ordered_unique_ids:
            return 0

        logger.info(f"Beginning reprocessing for {len(ordered_unique_ids)} transaction(s).")

        transactions_to_replay = await self._reader.list_transactions_to_replay(ordered_unique_ids)
        if not transactions_to_replay:
            _log_no_matching_transactions(ordered_unique_ids)
            return 0

        correlation = ReplayCorrelationMetadata(
            correlation_id=_resolved_replay_correlation_id(correlation_id),
            ingestion_job_id=normalize_ingestion_job_id(ingestion_job_id_var.get()),
            repair_delivery_id=repair_delivery_id,
        )
        plan = plan_transaction_replay(
            transactions=transactions_to_replay,
            correlation=correlation,
        )
        replayed_count = int(
            publish_transaction_replay_plan(
                plan=plan,
                publisher=self._publisher,
            )
        )
        logger.info(f"Successfully republished {replayed_count} transaction event(s).")

        return replayed_count


class SqlAlchemyTransactionReplayReader(TransactionReplayReader):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_transactions_to_replay(
        self,
        ordered_transaction_ids: list[str],
    ) -> list[Any]:
        result = await self._db.execute(_transactions_to_replay_stmt(ordered_transaction_ids))
        return [SimpleNamespace(**row) for row in result.mappings().all()]


class KafkaTransactionReplayPublisher(TransactionReplayPublisher):
    def __init__(self, kafka_producer: KafkaProducer) -> None:
        self._kafka_producer = kafka_producer

    def publish_replay_message(self, message: TransactionReplayMessage) -> None:
        logger.info(
            "Republishing event for transaction.",
            extra={
                "transaction_id": message.transaction_id,
                "topic": message.topic,
            },
        )
        self._kafka_producer.publish_message(
            topic=message.topic,
            key=message.key,
            value=message.payload,
            headers=message.headers,
        )

    def confirm_replay_delivery(self) -> int:
        return int(self._kafka_producer.flush() or 0)


def _transactions_to_replay_stmt(ordered_transaction_ids: list[str]) -> Any:
    ordering = case(
        {transaction_id: index for index, transaction_id in enumerate(ordered_transaction_ids)},
        value=DBTransaction.transaction_id,
    )
    return (
        select(
            *(
                DBTransaction.__table__.columns[field_name]
                for field_name in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
                if field_name in DBTransaction.__table__.columns
            ),
            Portfolio.tenant_id.label("tenant_id"),
        )
        .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
        .where(DBTransaction.transaction_id.in_(ordered_transaction_ids))
        .order_by(ordering)
    )


def _log_no_matching_transactions(ordered_transaction_ids: list[str]) -> None:
    logger.warning(
        "No matching transactions found in the database for the given IDs.",
        extra={"transaction_ids": ordered_transaction_ids},
    )


def _resolved_replay_correlation_id(correlation_id: str | None) -> str | None:
    if correlation_id is not None:
        return cast(str | None, normalize_lineage_value(correlation_id))
    return cast(str | None, normalize_lineage_value(correlation_id_var.get()))
