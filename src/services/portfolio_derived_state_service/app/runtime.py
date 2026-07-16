"""Supervised runtime for position and portfolio derived-state materialization."""

from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
    KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
    KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
)
from portfolio_common.health_server import health_probe_bind_host
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.runtime_providers import UuidIdGenerator
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

from .application.aggregation_jobs import AggregationScheduler, ProcessClaimedAggregationJobs
from .application.portfolio_timeseries import MaterializePortfolioTimeseries
from .application.position_timeseries import MaterializePositionTimeseries
from .delivery.valuation_snapshots import PositionTimeseriesConsumer
from .infrastructure.aggregation_scheduler_adapters import (
    PrometheusAggregationSchedulerMetricsSink,
    SqlAlchemyAggregationSchedulerRepositoryProvider,
    SystemAggregationSchedulerClock,
)
from .infrastructure.portfolio_timeseries_unit_of_work_provider import (
    SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider,
)
from .infrastructure.position_timeseries_repository_provider import (
    SqlAlchemyPositionTimeseriesRepositoryProvider,
)
from .settings import get_aggregation_runtime_settings
from .web import WORKER_READINESS_SERVICE_NAME
from .web import app as web_app

logger = logging.getLogger(__name__)

POSITION_TIMESERIES_CONSUMER_GROUP = "timeseries_generator_group_positions"
HEALTH_PORT = 8085


class PortfolioDerivedStateRuntime:
    """Supervise valuation delivery, aggregation workers, outbox, and health probes."""

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[object]] = []
        self._shutdown_event = asyncio.Event()
        self.consumers = [self._position_timeseries_consumer()]

        settings = get_aggregation_runtime_settings()
        id_generator = UuidIdGenerator()
        job_processor = ProcessClaimedAggregationJobs(
            materializer=MaterializePortfolioTimeseries(
                unit_of_work_provider=SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()
            ),
            worker_count=settings.portfolio_aggregation_worker_count,
        )
        self.scheduler = AggregationScheduler(
            poll_interval_seconds=settings.aggregation_scheduler_poll_interval_seconds,
            batch_size=settings.aggregation_scheduler_batch_size,
            lease_duration_seconds=settings.aggregation_job_lease_duration_seconds,
            max_attempts=settings.aggregation_scheduler_max_attempts,
            lease_owner=f"portfolio-derived-state-{id_generator.new_hex()}",
            repository_provider=SqlAlchemyAggregationSchedulerRepositoryProvider(),
            job_processor=job_processor,
            metrics_sink=PrometheusAggregationSchedulerMetricsSink(),
            clock=SystemAggregationSchedulerClock(),
            token_generator=id_generator,
        )
        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

    @staticmethod
    def _position_timeseries_consumer() -> PositionTimeseriesConsumer:
        materializer = MaterializePositionTimeseries(
            repository_provider=SqlAlchemyPositionTimeseriesRepositoryProvider()
        )
        return PositionTimeseriesConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            topic=KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
            group_id=POSITION_TIMESERIES_CONSUMER_GROUP,
            dlq_topic=KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
            service_prefix="PDS",
            use_case=materializer,
        )

    def _signal_handler(self, signum: int, _frame: object) -> None:
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self) -> None:
        """Run all critical components until shutdown or one component fails."""

        ensure_topics_exist(
            [
                KAFKA_VALUATION_SNAPSHOT_PERSISTED_TOPIC,
                KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC,
                KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
                KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
            ]
        )
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        server = uvicorn.Server(
            uvicorn.Config(
                web_app,
                host=health_probe_bind_host(),
                port=HEALTH_PORT,
                log_config=None,
            )
        )
        self.tasks = [
            *(asyncio.create_task(consumer.run()) for consumer in self.consumers),
            asyncio.create_task(self.scheduler.run()),
            asyncio.create_task(self.dispatcher.run()),
            asyncio.create_task(server.serve()),
        ]
        runtime_error = await wait_for_shutdown_or_task_failure(
            tasks=self.tasks,
            shutdown_event=self._shutdown_event,
            logger=logger,
            readiness_service_name=WORKER_READINESS_SERVICE_NAME,
        )
        await shutdown_runtime_components(
            tasks=self.tasks,
            consumers=self.consumers,
            stop_callbacks=[self.scheduler.stop, self.dispatcher.stop],
            server=server,
        )
        if runtime_error is not None:
            raise runtime_error
