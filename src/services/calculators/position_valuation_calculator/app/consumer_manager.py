# services/calculators/position-valuation-calculator/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
    KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC,
    KAFKA_VALUATION_REQUIRED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

from .consumers.price_event_consumer import PriceEventConsumer

# --- END NEW IMPORTS ---
from .consumers.valuation_consumer import ValuationConsumer
from .consumers.valuation_readiness_consumer import ValuationReadinessConsumer

# --- NEW IMPORTS ---
from .core.reprocessing_worker import ReprocessingWorker
from .core.valuation_scheduler import ValuationScheduler
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers, the outbox dispatcher,
    the new valuation scheduler, and the health probe web server.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        group_id = "position_valuation_group"
        service_prefix = "VAL"

        self.consumers.append(
            ValuationConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_VALUATION_REQUIRED_TOPIC,
                group_id=f"{group_id}_jobs",
                service_prefix=service_prefix,
            )
        )
        self.consumers.append(
            ValuationReadinessConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_DAY_READY_FOR_VALUATION_TOPIC,
                group_id=f"{group_id}_readiness",
                service_prefix=service_prefix,
            )
        )

        # --- Add back the PriceEventConsumer ---
        self.consumers.append(
            PriceEventConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                group_id=f"{group_id}_price_events",
                service_prefix=service_prefix,
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)
        self.scheduler = ValuationScheduler()
        # --- NEW: Instantiate the worker ---
        self.reprocessing_worker = ReprocessingWorker()

        logger.info(
            "ConsumerManager initialized with "
            f"{len(self.consumers)} consumer(s), 1 scheduler, "
            "and 1 reprocessing worker."
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
            "Starting all consumer tasks, the outbox dispatcher, "
            "the scheduler, the reprocessing worker, and the web server..."
        )
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(self.scheduler.run()))
        # --- NEW: Add the worker to the asyncio tasks ---
        self.tasks.append(asyncio.create_task(self.reprocessing_worker.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        logger.info("ConsumerManager is running. Press Ctrl+C to exit.")
        await self._shutdown_event.wait()

        logger.info("Shutdown event received. Stopping all tasks...")
        for consumer in self.consumers:
            consumer.shutdown()

        self.dispatcher.stop()
        self.scheduler.stop()
        # --- NEW: Stop the worker ---
        self.reprocessing_worker.stop()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info(
            "All consumer, dispatcher, and web server tasks have been successfully shut down."
        )
