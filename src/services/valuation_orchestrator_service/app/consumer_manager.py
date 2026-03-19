import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_MARKET_PRICES_PERSISTED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumers.price_event_consumer import PriceEventConsumer
from .consumers.valuation_readiness_consumer import ValuationReadinessConsumer
from .core.reprocessing_worker import ReprocessingWorker
from .core.valuation_scheduler import ValuationScheduler
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Valuation orchestrator runtime.

    Owns readiness ingestion, back-dated price triggers, scheduler dispatch,
    and durable reprocessing workflows. No valuation compute is executed here.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        group_id = "valuation_orchestrator_group"
        service_prefix = "VAL-ORCH"
        dlq_topic = KAFKA_PERSISTENCE_DLQ_TOPIC

        self.consumers.append(
            ValuationReadinessConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
                group_id=f"{group_id}_readiness",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
            )
        )
        self.consumers.append(
            PriceEventConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_MARKET_PRICES_PERSISTED_TOPIC,
                group_id=f"{group_id}_price_events",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
            )
        )

        self.scheduler = ValuationScheduler()
        self.reprocessing_worker = ReprocessingWorker()

        logger.info(
            "ConsumerManager initialized with %s consumer(s), scheduler, and reprocessing worker.",
            len(self.consumers),
        )

    def _signal_handler(self, signum, frame):
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8087, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
        self.tasks.append(asyncio.create_task(self.scheduler.run()))
        self.tasks.append(asyncio.create_task(self.reprocessing_worker.run()))
        self.tasks.append(asyncio.create_task(server.serve()))

        runtime_error = await wait_for_shutdown_or_task_failure(
            tasks=self.tasks,
            shutdown_event=self._shutdown_event,
            logger=logger,
        )

        await shutdown_runtime_components(
            tasks=self.tasks,
            consumers=self.consumers,
            stop_callbacks=[self.scheduler.stop, self.reprocessing_worker.stop],
            server=server,
        )
        if runtime_error is not None:
            raise runtime_error
