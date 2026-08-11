"""Run the bounded PostgreSQL-backed corporate-action release poller."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from time import monotonic

from asyncpg import (
    AdminShutdownError,
    CannotConnectNowError,
    CrashShutdownError,
    PostgresConnectionError,
    TooManyConnectionsError,
)
from sqlalchemy.exc import SQLAlchemyError

from ..application import (
    CorporateActionReleaseWorkerStatus,
    ProcessNextCorporateActionReleaseUseCase,
    TransactionProcessingError,
)
from ..ports.corporate_action_release_observability import (
    NOOP_CORPORATE_ACTION_RELEASE_OBSERVER,
    CorporateActionReleaseCycleOutcome,
    CorporateActionReleaseObserver,
)

logger = logging.getLogger(__name__)

_RETRYABLE_DATABASE_ERRORS = (
    SQLAlchemyError,
    ConnectionError,
    PostgresConnectionError,
    CannotConnectNowError,
    AdminShutdownError,
    CrashShutdownError,
    TooManyConnectionsError,
)


class CorporateActionReleaseWorker:
    """Poll durable release work without holding database transactions while idle."""

    def __init__(
        self,
        use_case: ProcessNextCorporateActionReleaseUseCase,
        *,
        idle_poll_seconds: float = 0.25,
        retry_backoff_seconds: float = 1.0,
        observer: CorporateActionReleaseObserver = NOOP_CORPORATE_ACTION_RELEASE_OBSERVER,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if idle_poll_seconds <= 0 or retry_backoff_seconds <= 0:
            raise ValueError("corporate-action worker intervals must be positive")
        self._use_case = use_case
        self._idle_poll_seconds = idle_poll_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._observer = observer
        self._clock = clock
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            started_at = self._clock()
            try:
                result = await self._use_case.execute()
            except TransactionProcessingError as exc:
                if not exc.retryable:
                    raise
                self._observe_cycle(
                    CorporateActionReleaseCycleOutcome.RETRYABLE_ERROR,
                    started_at,
                )
                logger.warning(
                    "Corporate-action release worker will retry durable work.",
                    extra={"reason_code": exc.reason_code},
                )
                await self._wait(self._retry_backoff_seconds)
                continue
            except _RETRYABLE_DATABASE_ERRORS:
                self._observe_cycle(
                    CorporateActionReleaseCycleOutcome.DATABASE_ERROR,
                    started_at,
                )
                logger.exception(
                    "Corporate-action release worker will retry after a database failure."
                )
                await self._wait(self._retry_backoff_seconds)
                continue
            self._observe_cycle(
                CorporateActionReleaseCycleOutcome(result.status.value.lower()),
                started_at,
            )
            if result.status is CorporateActionReleaseWorkerStatus.IDLE:
                await self._wait(self._idle_poll_seconds)
            elif result.status is CorporateActionReleaseWorkerStatus.FAILED:
                logger.error(
                    "Corporate-action release entered terminal failure.",
                    extra={
                        "release_id": result.release_id,
                        "execution_ordinal": result.execution_ordinal,
                        "transaction_id": result.transaction_id,
                    },
                )

    def stop(self) -> None:
        """Signal shutdown synchronously for the shared runtime callback contract."""

        self._stopped.set()

    async def _wait(self, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=timeout_seconds)
        except TimeoutError:
            pass

    def _observe_cycle(
        self,
        outcome: CorporateActionReleaseCycleOutcome,
        started_at: float,
    ) -> None:
        try:
            self._observer.observe_cycle(
                outcome,
                max(self._clock() - started_at, 0.0),
            )
        except Exception:
            logger.exception("Corporate-action release worker metric recording failed.")
