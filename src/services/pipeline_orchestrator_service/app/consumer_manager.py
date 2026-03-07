import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CASHFLOW_CALCULATED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC,
    KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

from .consumers.cashflow_stage_consumer import CashflowStageConsumer
from .consumers.processed_transaction_stage_consumer import ProcessedTransactionStageConsumer
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        self.consumers.append(
            ProcessedTransactionStageConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                group_id="pipeline_orchestrator_processed_txn_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )
        self.consumers.append(
            CashflowStageConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_CASHFLOW_CALCULATED_TOPIC,
                group_id="pipeline_orchestrator_cashflow_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )

        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

    def _signal_handler(self, signum, frame):
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        required_topics.append(KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC)
        required_topics.append(KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC)
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8086, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        await self._shutdown_event.wait()

        for consumer in self.consumers:
            consumer.shutdown()
        self.dispatcher.stop()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
