# services/calculators/position_calculator/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

from .consumers.transaction_event_consumer import TransactionEventConsumer
from .web import app as web_app  # NEW IMPORT

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers, the outbox dispatcher,
    and the new health probe web server.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        self.consumers.append(
            TransactionEventConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTION_PROCESSING_COMPLETED_TOPIC,
                group_id="position_calculator_group_gated",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="POS",
            )
        )

        # Replay and backdated correction flow currently emits processed transaction events.
        self.consumers.append(
            TransactionEventConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                group_id="position_calculator_group_replay",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="POS",
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)

        logger.info(f"ConsumerManager initialized with {len(self.consumers)} consumer(s).")

    def _signal_handler(self, signum, frame):
        logger.info(
            "Received shutdown signal: "
            f"{signal.Signals(signum).name}. Initiating graceful shutdown..."
        )
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # NEW: Setup and run the Uvicorn server for health probes
        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8081, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting all consumer tasks, the outbox dispatcher, and the web server...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()

        logger.info("Shutdown event received. Stopping all tasks...")
        for consumer in self.consumers:
            consumer.shutdown()

        self.dispatcher.stop()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All tasks have been successfully shut down.")
