# services/persistence-service/app/consumer_manager.py
import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_FX_RATES_RAW_RECEIVED_TOPIC,
    KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
    KAFKA_MARKET_PRICES_RAW_RECEIVED_TOPIC,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_BUSINESS_DATES_RAW_RECEIVED_TOPIC,
    KAFKA_PORTFOLIOS_RAW_RECEIVED_TOPIC,
    KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumers.business_date_consumer import BusinessDateConsumer
from .consumers.fx_rate_consumer import FxRateConsumer
from .consumers.instrument_consumer import InstrumentConsumer
from .consumers.market_price_consumer import MarketPriceConsumer
from .consumers.portfolio_consumer import PortfolioConsumer
from .consumers.transaction_consumer import TransactionPersistenceConsumer
from .monitoring import setup_metrics
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    """
    Manages the lifecycle of Kafka consumers, the outbox dispatcher,
    and the health probe web server.
    """

    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        # Setup web app and metrics first
        self.web_app = web_app
        custom_metrics = setup_metrics(self.web_app)

        dlq_topic = KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
        service_prefix = "PST"

        self.consumers.append(
            PortfolioConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIOS_RAW_RECEIVED_TOPIC,
                group_id="persistence_group_portfolios",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )
        self.consumers.append(
            TransactionPersistenceConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTIONS_RAW_RECEIVED_TOPIC,
                group_id="persistence_group_transactions",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )
        self.consumers.append(
            InstrumentConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_INSTRUMENTS_RECEIVED_TOPIC,
                group_id="persistence_group_instruments",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )
        self.consumers.append(
            MarketPriceConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_MARKET_PRICES_RAW_RECEIVED_TOPIC,
                group_id="persistence_group_market_prices",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )
        self.consumers.append(
            FxRateConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_FX_RATES_RAW_RECEIVED_TOPIC,
                group_id="persistence_group_fx_rates",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )
        self.consumers.append(
            BusinessDateConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_BUSINESS_DATES_RAW_RECEIVED_TOPIC,
                group_id="persistence_group_business_dates",
                dlq_topic=dlq_topic,
                service_prefix=service_prefix,
                metrics=custom_metrics,
            )
        )

        kafka_producer = get_kafka_producer()
        self.dispatcher = OutboxDispatcher(kafka_producer=kafka_producer)

        logger.info("ConsumerManager initialized", extra={"num_consumers": len(self.consumers)})

    def _signal_handler(self, signum, frame):
        """Sets the shutdown event when a signal is received."""
        logger.info("Shutdown signal received", extra={"signal": signal.Signals(signum).name})
        self._shutdown_event.set()

    async def run(self):
        """
        The main execution function. Sets up signal handling and runs all concurrent tasks.
        """
        required_topics = [consumer.topic for consumer in self.consumers]
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(self.web_app, host="0.0.0.0", port=8080, log_config=None)
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
        logger.info(
            "All consumer, dispatcher, and web server tasks have been successfully shut down."
        )
        if runtime_error is not None:
            raise runtime_error
