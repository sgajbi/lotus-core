"""Bounded coordination helpers for concurrency tests."""

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

T = TypeVar("T")


async def wait_for_task_signal(
    task: asyncio.Task[T],
    signal: asyncio.Event,
    *,
    timeout: float,
) -> None:
    """Wait for ``signal`` while propagating an early task failure.

    A plain event wait loses the producer's exception when the producer fails before
    setting the event. Supervising both awaitables makes that failure immediate and
    keeps the timeout as a bound for a genuinely stuck producer.
    """

    signal_task = asyncio.create_task(signal.wait())
    try:
        done, _ = await asyncio.wait(
            {task, signal_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            task.result()
            if not signal.is_set():
                raise RuntimeError("task completed before publishing its coordination signal")
        if signal_task in done:
            signal_task.result()
        elif not signal.is_set():
            raise TimeoutError("timed out waiting for task coordination signal")
    finally:
        if not signal_task.done():
            signal_task.cancel()
        await asyncio.gather(signal_task, return_exceptions=True)


async def cancel_pending_tasks(*tasks: Awaitable[object] | None) -> None:
    """Cancel and await unfinished tasks without masking the original test failure."""

    concrete_tasks = [task for task in tasks if isinstance(task, asyncio.Task)]
    for task in concrete_tasks:
        if not task.done():
            task.cancel()
    if concrete_tasks:
        await asyncio.gather(*concrete_tasks, return_exceptions=True)


async def wait_for_postgres_advisory_lock_wait(
    task: asyncio.Task[T],
    session_factory: async_sessionmaker[AsyncSession],
    *,
    backend_pid: int,
    timeout: float,
) -> None:
    """Wait until PostgreSQL exposes ``task`` as waiting for an advisory lock.

    Database state, rather than elapsed time or client call ordering, proves that
    the request reached PostgreSQL and could not acquire its advisory lock. The
    producer task remains supervised so an early database failure is propagated.
    """

    async def observe_wait() -> bool:
        async with session_factory() as observer_session:
            return bool(
                await observer_session.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_locks
                            WHERE pid = :backend_pid
                              AND locktype = 'advisory'
                              AND NOT granted
                        )
                        """
                    ),
                    {"backend_pid": backend_pid},
                )
            )

    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"task did not enter a PostgreSQL advisory-lock wait within {timeout} seconds"
            )

        observation_task = asyncio.create_task(observe_wait())
        try:
            done, _ = await asyncio.wait(
                {task, observation_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                await task
                raise RuntimeError(
                    "task completed without entering a PostgreSQL advisory-lock wait"
                )
            if observation_task not in done:
                raise TimeoutError(
                    f"PostgreSQL advisory-lock observation exceeded the {timeout}-second wait bound"
                )
            if observation_task.result():
                return
        finally:
            if not observation_task.done():
                observation_task.cancel()
            await asyncio.gather(observation_task, return_exceptions=True)

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"task did not enter a PostgreSQL advisory-lock wait within {timeout} seconds"
            )
        await asyncio.sleep(min(0.01, remaining))
