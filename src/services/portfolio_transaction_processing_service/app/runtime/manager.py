from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Sequence
from typing import Any

import uvicorn
from portfolio_common.kafka_admin import ensure_topics_exist
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.worker_runtime import run_kafka_worker_runtime

from ..web import WORKER_READINESS_SERVICE_NAME
from ..web import app as web_app
from .consumer_composition import build_transaction_processing_consumers

logger = logging.getLogger(__name__)


class ConsumerManager:
    def __init__(
        self,
        *,
        consumers: Sequence[Any] | None = None,
        dispatcher: Any | None = None,
    ) -> None:
        self.consumers = list(
            consumers if consumers is not None else build_transaction_processing_consumers()
        )
        self.dispatcher = (
            dispatcher
            if dispatcher is not None
            else OutboxDispatcher(kafka_producer=get_kafka_producer())
        )
        self.tasks: list[asyncio.Task[Any]] = []
        self._shutdown_event = asyncio.Event()

    def _signal_handler(self, signum: int, _frame: object) -> None:
        logger.info(
            "Received shutdown signal.",
            extra={"signal": signal.Signals(signum).name},
        )
        self._shutdown_event.set()

    async def run(self) -> None:
        await run_kafka_worker_runtime(
            consumers=self.consumers,
            dispatcher=self.dispatcher,
            web_app=web_app,
            web_port=8085,
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
