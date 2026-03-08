import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC,
    KAFKA_VALUATION_DAY_COMPLETED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import wait_for_shutdown_or_task_failure

from .consumers.position_timeseries_consumer import PositionTimeseriesConsumer
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Position timeseries worker runtime.

    Owns position-timeseries generation and completion publication.
    Portfolio aggregation dispatch and aggregation execution are delegated to
    portfolio_aggregation_service.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        dlq_topic = KAFKA_PERSISTENCE_DLQ_TOPIC
        service_prefix = "TS"

        self.consumers.append(
            PositionTimeseriesConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                group_id="timeseries_generator_group_positions",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
            )
        )
        self.consumers.append(
            PositionTimeseriesConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_VALUATION_DAY_COMPLETED_TOPIC,
                group_id="timeseries_generator_group_positions_gate",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
            )
        )

        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

        logger.info(
            "ConsumerManager initialized with %s position-timeseries consumer(s).",
            len(self.consumers),
        )

    def _signal_handler(self, signum, frame):
        logger.info(
            "Received shutdown signal: %s. Initiating graceful shutdown...",
            signal.Signals(signum).name,
        )
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        required_topics.append(KAFKA_POSITION_TIMESERIES_DAY_COMPLETED_TOPIC)
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8085, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        logger.info("Starting position-timeseries consumer(s), dispatcher, and the web server...")
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
        for consumer in self.consumers:
            consumer.shutdown()
        self.dispatcher.stop()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All tasks have been successfully shut down.")
        if runtime_error is not None:
            raise runtime_error
