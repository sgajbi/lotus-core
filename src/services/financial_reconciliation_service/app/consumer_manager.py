import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.runtime_supervision import wait_for_shutdown_or_task_failure

from .consumers.reconciliation_requested_consumer import ReconciliationRequestedConsumer
from .main import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    def __init__(self):
        self.consumers = [
            ReconciliationRequestedConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_FINANCIAL_RECONCILIATION_REQUESTED_TOPIC,
                group_id="financial_reconciliation_requested_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="FRC",
            )
        ]
        self.tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

    def _signal_handler(self, signum, frame):
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self):
        ensure_topics_exist([consumer.topic for consumer in self.consumers])

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8010, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(server.serve()))

        runtime_error = await wait_for_shutdown_or_task_failure(
            tasks=self.tasks,
            shutdown_event=self._shutdown_event,
            logger=logger,
        )

        for consumer in self.consumers:
            consumer.shutdown()
        server.should_exit = True

        await asyncio.gather(*self.tasks, return_exceptions=True)
        if runtime_error is not None:
            raise runtime_error
