import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumers.portfolio_timeseries_consumer import PortfolioTimeseriesConsumer
from .core.aggregation_scheduler import AggregationScheduler
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Portfolio aggregation runtime.

    Owns aggregation job dispatch, portfolio-level timeseries aggregation,
    and completion publication for aggregation stages.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        self.consumers.append(
            PortfolioTimeseriesConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC,
                group_id="portfolio_aggregation_group",
                dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
                service_prefix="PTA",
            )
        )

        self.scheduler = AggregationScheduler()
        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

        logger.info(
            (
                "ConsumerManager initialized with %s portfolio aggregation consumer(s) "
                "and 1 scheduler."
            ),
            len(self.consumers),
        )

    def _signal_handler(self, signum, frame):
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self):
        ensure_topics_exist(
            [consumer.topic for consumer in self.consumers]
            + [KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC]
        )

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8088, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.scheduler.run()))
        self.tasks.append(asyncio.create_task(self.dispatcher.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        runtime_error = await wait_for_shutdown_or_task_failure(
            tasks=self.tasks,
            shutdown_event=self._shutdown_event,
            logger=logger,
        )

        await shutdown_runtime_components(
            tasks=self.tasks,
            consumers=self.consumers,
            stop_callbacks=[self.scheduler.stop, self.dispatcher.stop],
            server=server,
        )
        if runtime_error is not None:
            raise runtime_error
