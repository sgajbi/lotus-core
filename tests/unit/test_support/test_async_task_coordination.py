"""Prove bounded test-task coordination and cleanup semantics."""

import asyncio

import pytest

from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_task_signal,
)

pytestmark = pytest.mark.asyncio


async def test_wait_for_task_signal_returns_after_signal() -> None:
    signal = asyncio.Event()
    release = asyncio.Event()

    async def producer() -> None:
        signal.set()
        await release.wait()

    task = asyncio.create_task(producer())
    try:
        await wait_for_task_signal(task, signal, timeout=1)
    finally:
        release.set()
        await cancel_pending_tasks(task)


async def test_wait_for_task_signal_propagates_producer_failure() -> None:
    signal = asyncio.Event()

    async def producer() -> None:
        raise ConnectionError("database connection failed")

    task = asyncio.create_task(producer())
    with pytest.raises(ConnectionError, match="database connection failed"):
        await wait_for_task_signal(task, signal, timeout=1)
    await cancel_pending_tasks(task)


async def test_wait_for_task_signal_propagates_acquisition_failure() -> None:
    signal = asyncio.Event()

    async def producer() -> None:
        raise RuntimeError("advisory fence acquisition failed")

    task = asyncio.create_task(producer())
    with pytest.raises(RuntimeError, match="advisory fence acquisition failed"):
        await wait_for_task_signal(task, signal, timeout=1)
    await cancel_pending_tasks(task)


async def test_wait_for_task_signal_rejects_success_without_signal() -> None:
    signal = asyncio.Event()

    async def producer() -> None:
        return None

    task = asyncio.create_task(producer())
    with pytest.raises(RuntimeError, match="before publishing"):
        await wait_for_task_signal(task, signal, timeout=1)
    await cancel_pending_tasks(task)


async def test_wait_for_task_signal_times_out_and_cleanup_cancels_producer() -> None:
    signal = asyncio.Event()

    async def producer() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(producer())
    with pytest.raises(TimeoutError, match="coordination signal"):
        await wait_for_task_signal(task, signal, timeout=0.01)

    await cancel_pending_tasks(task)
    assert task.cancelled()
