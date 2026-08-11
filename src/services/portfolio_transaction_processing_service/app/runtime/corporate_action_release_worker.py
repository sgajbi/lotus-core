"""Run the bounded PostgreSQL-backed corporate-action release poller."""

from __future__ import annotations

import asyncio
import logging

from ..application import (
    CorporateActionReleaseWorkerStatus,
    ProcessNextCorporateActionReleaseUseCase,
    TransactionProcessingError,
)

logger = logging.getLogger(__name__)


class CorporateActionReleaseWorker:
    """Poll durable release work without holding database transactions while idle."""

    def __init__(
        self,
        use_case: ProcessNextCorporateActionReleaseUseCase,
        *,
        idle_poll_seconds: float = 0.25,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        if idle_poll_seconds <= 0 or retry_backoff_seconds <= 0:
            raise ValueError("corporate-action worker intervals must be positive")
        self._use_case = use_case
        self._idle_poll_seconds = idle_poll_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                result = await self._use_case.execute()
            except TransactionProcessingError as exc:
                if not exc.retryable:
                    raise
                logger.warning(
                    "Corporate-action release worker will retry durable work.",
                    extra={"reason_code": exc.reason_code},
                )
                await self._wait(self._retry_backoff_seconds)
                continue
            if result.status is CorporateActionReleaseWorkerStatus.IDLE:
                await self._wait(self._idle_poll_seconds)

    async def stop(self) -> None:
        self._stopped.set()

    async def _wait(self, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=timeout_seconds)
        except TimeoutError:
            pass
