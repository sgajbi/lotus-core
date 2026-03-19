# services/calculators/cost_calculator_service/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumer import CostCalculatorConsumer
from .consumers.reprocessing_consumer import ReprocessingConsumer
from .web import app as web_app

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
            CostCalculatorConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
                group_id="cost_calculator_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="COST",
            )
        )

        # Add the new reprocessing consumer
        self.consumers.append(
            ReprocessingConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
                group_id="cost_reprocessing_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,  # Share DLQ for now
                service_prefix="COST_REPRO",
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

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8083, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting all consumer tasks, the outbox dispatcher, and the web server...")
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        runtime_error = await wait_for_shutdown_or_task_failure(
            tasks=self.tasks,
            shutdown_event=self._shutdown_event,
            logger=logger,
        )

        logger.info("Shutdown event received. Stopping all tasks...")
        await shutdown_runtime_components(
            tasks=self.tasks,
            consumers=self.consumers,
            stop_callbacks=[self.dispatcher.stop],
            server=server,
        )
        logger.info("All consumer and dispatcher tasks have been successfully shut down.")
        if runtime_error is not None:
            raise runtime_error
