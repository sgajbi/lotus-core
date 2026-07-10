from __future__ import annotations

from collections.abc import Callable

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from portfolio_common.kafka_consumer import BaseConsumer

from ..application import ProcessTransactionUseCase, ReplayBookedTransactionUseCase
from ..delivery.kafka import (
    BookedTransactionReplayRequestConsumer,
    TransactionProcessingConsumer,
)
from ..infrastructure import (
    build_process_transaction_use_case,
    build_replay_booked_transaction_use_case,
)

TRANSACTION_PROCESSING_CONSUMER_GROUP = "portfolio_transaction_processing_group"
TRANSACTION_REPLAY_REQUEST_CONSUMER_GROUP = "portfolio_transaction_replay_request_group"

ConsumerFactory = Callable[..., BaseConsumer]


def build_transaction_processing_consumers(
    *,
    process_transaction: ProcessTransactionUseCase | None = None,
    replay_booked_transaction: ReplayBookedTransactionUseCase | None = None,
    transaction_consumer_factory: ConsumerFactory = TransactionProcessingConsumer,
    replay_request_consumer_factory: ConsumerFactory = BookedTransactionReplayRequestConsumer,
) -> tuple[BaseConsumer, BaseConsumer]:
    """Compose one live and one replay-request consumer for the final deployable."""
    process_use_case = (
        process_transaction
        if process_transaction is not None
        else build_process_transaction_use_case()
    )
    replay_use_case = (
        replay_booked_transaction
        if replay_booked_transaction is not None
        else build_replay_booked_transaction_use_case()
    )
    shared = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "dlq_topic": KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    }
    live_consumer = transaction_consumer_factory(
        **shared,
        topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
        group_id=TRANSACTION_PROCESSING_CONSUMER_GROUP,
        service_prefix="TXNPROC",
        use_case=process_use_case,
    )
    replay_consumer = replay_request_consumer_factory(
        **shared,
        topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
        group_id=TRANSACTION_REPLAY_REQUEST_CONSUMER_GROUP,
        service_prefix="TXNREPLAY",
        use_case=replay_use_case,
    )
    return live_consumer, replay_consumer
