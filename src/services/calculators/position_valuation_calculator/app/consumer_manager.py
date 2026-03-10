# services/calculators/position-valuation-calculator/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_VALUATION_REQUIRED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumers.valuation_consumer import ValuationConsumer
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Valuation worker runtime.

    Owns valuation compute execution and stage-completion publication.
    Scheduling and reprocessing orchestration are delegated to
    valuation_orchestrator_service.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        group_id = "position_valuation_worker_group"
        service_prefix = "VAL"

        self.consumers.append(
            ValuationConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_VALUATION_REQUIRED_TOPIC,
                group_id=group_id,
                service_prefix=service_prefix,
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)

        logger.info(
            "ConsumerManager initialized with %s valuation worker consumer(s).",
            len(self.consumers),
        )

    def _signal_handler(self, signum, frame):
        """Sets the shutdown event when a signal is received."""
        logger.info(
            "Received shutdown signal: "
            f"{signal.Signals(signum).name}. Initiating graceful shutdown..."
        )
        self._shutdown_event.set()

    async def run(self):
        """
        The main execution function.
        """
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8084, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info(
            "Starting valuation worker consumer(s), outbox dispatcher, and web server..."
        )
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
        logger.info(
            "All consumer, dispatcher, and web server tasks have been successfully shut down."
        )
        if runtime_error is not None:
            raise runtime_error
