# services/calculators/cost_calculator_service/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_TRANSACTIONS_PERSISTED_TOPIC,
    KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.worker_runtime import run_kafka_worker_runtime

from .consumer import CostCalculatorConsumer
from .consumers.reprocessing_consumer import ReprocessingConsumer
from .web import WORKER_READINESS_SERVICE_NAME
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
                dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
                service_prefix="COST",
            )
        )

        # Add the new reprocessing consumer
        self.consumers.append(
            ReprocessingConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTIONS_REPROCESSING_REQUESTED_TOPIC,
                group_id="cost_reprocessing_group",
                dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,  # Share DLQ for now
                service_prefix="COST_REPRO",
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)

        logger.info(f"ConsumerManager initialized with {len(self.consumers)} consumer(s).")

    def _signal_handler(self, signum, _frame):
        logger.info(
            "Received shutdown signal: "
            f"{signal.Signals(signum).name}. Initiating graceful shutdown..."
        )
        self._shutdown_event.set()

    async def run(self):
        await run_kafka_worker_runtime(
            consumers=self.consumers,
            dispatcher=self.dispatcher,
            web_app=web_app,
            web_port=8083,
            readiness_service_name=WORKER_READINESS_SERVICE_NAME,
            shutdown_event=self._shutdown_event,
            signal_handler=self._signal_handler,
            tasks=self.tasks,
            logger=logger,
            ensure_topics=ensure_topics_exist,
            signal_module=signal,
            server_config_factory=uvicorn.Config,
            server_factory=uvicorn.Server,
        )
