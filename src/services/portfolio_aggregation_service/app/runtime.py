"""Runtime composition for portfolio derived-state aggregation."""

from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn
from portfolio_common.config import (
    KAFKA_PORTFOLIO_DAY_AGGREGATION_COMPLETED_TOPIC,
    KAFKA_PORTFOLIO_DAY_RECONCILIATION_REQUESTED_TOPIC,
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
from .infrastructure.aggregation_scheduler_adapters import (
    PrometheusAggregationSchedulerMetricsSink,
    SqlAlchemyAggregationSchedulerRepositoryProvider,
    SystemAggregationSchedulerClock,
)
from .infrastructure.portfolio_timeseries_unit_of_work_provider import (
    SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider,
)
from .settings import get_aggregation_runtime_settings
from .web import WORKER_READINESS_SERVICE_NAME
from .web import app as web_app

logger = logging.getLogger(__name__)


class PortfolioAggregationRuntime:
    """Supervise durable aggregation workers, outbox delivery, and health probes."""

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[object]] = []
        self._shutdown_event = asyncio.Event()
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
            lease_owner=f"portfolio-aggregation-{id_generator.new_hex()}",
            repository_provider=SqlAlchemyAggregationSchedulerRepositoryProvider(),
            job_processor=job_processor,
            metrics_sink=PrometheusAggregationSchedulerMetricsSink(),
            clock=SystemAggregationSchedulerClock(),
            token_generator=id_generator,
        )
        self.dispatcher = OutboxDispatcher(kafka_producer=get_kafka_producer())

    def _signal_handler(self, signum: int, _frame: object) -> None:
        logger.info("Received shutdown signal: %s", signal.Signals(signum).name)
        self._shutdown_event.set()

    async def run(self) -> None:
        """Run critical components until shutdown or one component fails."""

        ensure_topics_exist(
            [
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
                port=8088,
                log_config=None,
            )
        )
        self.tasks = [
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
            consumers=[],
            stop_callbacks=[self.scheduler.stop, self.dispatcher.stop],
            server=server,
        )
        if runtime_error is not None:
            raise runtime_error
