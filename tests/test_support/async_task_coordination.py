"""Bounded coordination helpers for concurrency tests."""

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

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
