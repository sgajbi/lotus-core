"""Specify resilient lifecycle behavior for the corporate-action release poller."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncpg import (
    CannotConnectNowError,
    ConnectionDoesNotExistError,
    UniqueViolationError,
)
from sqlalchemy.exc import SQLAlchemyError

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionReleaseWorkerResult,
    CorporateActionReleaseWorkerStatus,
)
from src.services.portfolio_transaction_processing_service.app.ports.corporate_action_release_observability import (  # noqa: E501
    CorporateActionReleaseCycleOutcome,
)
from src.services.portfolio_transaction_processing_service.app.runtime.corporate_action_release_worker import (  # noqa: E501
    CorporateActionReleaseWorker,
)


@pytest.mark.asyncio
async def test_synchronous_stop_callback_ends_idle_worker_cleanly() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = CorporateActionReleaseWorkerResult(
        CorporateActionReleaseWorkerStatus.IDLE
    )
    worker = CorporateActionReleaseWorker(use_case, idle_poll_seconds=0.01)
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(use_case.execute, minimum=1)

    assert worker.stop() is None

    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_stop_allows_in_flight_member_to_finish_before_exit() -> None:
    started = asyncio.Event()
    finish = asyncio.Event()
    use_case = AsyncMock()

    async def execute() -> CorporateActionReleaseWorkerResult:
        started.set()
        await finish.wait()
        return CorporateActionReleaseWorkerResult(CorporateActionReleaseWorkerStatus.COMPLETE)

    use_case.execute.side_effect = execute
    observer = MagicMock()
    clock = MagicMock(side_effect=[10.0, 10.5])
    worker = CorporateActionReleaseWorker(use_case, observer=observer, clock=clock)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), timeout=1)

    worker.stop()
    assert not task.done()
    finish.set()

    await asyncio.wait_for(task, timeout=1)
    assert use_case.execute.await_count == 1
    observer.observe_cycle.assert_called_once_with(
        CorporateActionReleaseCycleOutcome.COMPLETE,
        0.5,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "database_error",
    [
        SQLAlchemyError("database unavailable"),
        CannotConnectNowError("database is restarting"),
        ConnectionDoesNotExistError("database connection was interrupted"),
    ],
    ids=("sqlalchemy", "postgres-restart", "postgres-connection-loss"),
)
async def test_database_failure_retries_without_terminating_runtime(
    database_error: Exception,
) -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = [
        database_error,
        CorporateActionReleaseWorkerResult(CorporateActionReleaseWorkerStatus.IDLE),
    ]
    worker = CorporateActionReleaseWorker(
        use_case,
        idle_poll_seconds=0.01,
        retry_backoff_seconds=0.01,
    )
    task = asyncio.create_task(worker.run())
    await _wait_for_calls(use_case.execute, minimum=2)

    worker.stop()

    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_non_transient_driver_error_terminates_worker() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = UniqueViolationError("constraint violation")
    worker = CorporateActionReleaseWorker(use_case)

    with pytest.raises(UniqueViolationError, match="constraint violation"):
        await worker.run()


async def _wait_for_calls(mock: AsyncMock, *, minimum: int) -> None:
    for _ in range(100):
        if mock.await_count >= minimum:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"worker did not execute {minimum} time(s)")
