import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CASHFLOWS_CALCULATED_TOPIC,
    KAFKA_PERSISTENCE_DLQ_TOPIC,
    KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
    KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
)
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .consumers.cashflow_stage_consumer import CashflowStageConsumer
from .consumers.financial_reconciliation_completion_consumer import (
    FinancialReconciliationCompletionConsumer,
)
from .consumers.portfolio_aggregation_stage_consumer import PortfolioAggregationStageConsumer
from .consumers.processed_transaction_stage_consumer import ProcessedTransactionStageConsumer
from .web import app as web_app

logger = logging.getLogger(__name__)


class ConsumerManager:
    def __init__(self):
        self.consumers = []
        self.tasks = []
        self._shutdown_event = asyncio.Event()

        self.consumers.append(
            ProcessedTransactionStageConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC,
                group_id="pipeline_orchestrator_processed_txn_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )
        self.consumers.append(
            CashflowStageConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_CASHFLOWS_CALCULATED_TOPIC,
                group_id="pipeline_orchestrator_cashflow_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )
        self.consumers.append(
            PortfolioAggregationStageConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
                group_id="pipeline_orchestrator_portfolio_aggregation_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )
        self.consumers.append(
            FinancialReconciliationCompletionConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                topic=KAFKA_PORTFOLIO_DAY_RECONCILIATION_COMPLETED_TOPIC,
                group_id="pipeline_orchestrator_reconciliation_completion_group",
                dlq_topic=KAFKA_PERSISTENCE_DLQ_TOPIC,
                service_prefix="PIPE",
            )
        )

        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

    def _signal_handler(self, signum, frame):
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self):
        required_topics = [consumer.topic for consumer in self.consumers]
        required_topics.append(KAFKA_TRANSACTION_PROCESSING_READY_TOPIC)
        required_topics.append(KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC)
        required_topics.append(KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC)
        required_topics.append(KAFKA_PORTFOLIO_DAY_CONTROLS_EVALUATED_TOPIC)
        ensure_topics_exist(required_topics)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        uvicorn_config = uvicorn.Config(web_app, host="0.0.0.0", port=8086, log_config=None)
        server = uvicorn.Server(uvicorn_config)

        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]
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
            stop_callbacks=[self.dispatcher.stop],
            server=server,
        )
        if runtime_error is not None:
            raise runtime_error
