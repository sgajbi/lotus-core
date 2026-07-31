"""Prove bounded test-task coordination and cleanup semantics."""

import asyncio

import pytest

from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)

pytestmark = pytest.mark.asyncio


class _ObserverSession:
    def __init__(self, scalar_result) -> None:
        self._scalar_result = scalar_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def scalar(self, statement, parameters):
        del statement, parameters
        if callable(self._scalar_result):
            return await self._scalar_result()
        return self._scalar_result


class _ObserverSessionFactory:
    def __init__(self, scalar_result) -> None:
        self._scalar_result = scalar_result

    def __call__(self) -> _ObserverSession:
        return _ObserverSession(self._scalar_result)


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


async def test_cancel_pending_tasks_bounds_cancellation_resistant_cleanup() -> None:
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def cancellation_resistant_task() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release_cleanup.wait()
            raise
        finally:
            cleanup_finished.set()

    task = asyncio.create_task(cancellation_resistant_task())
    await asyncio.sleep(0)
    await asyncio.wait_for(cancel_pending_tasks(task, timeout=0.01), timeout=0.1)
    assert task.done() is False

    release_cleanup.set()
    await asyncio.wait_for(cleanup_finished.wait(), timeout=0.1)
    await asyncio.gather(task, return_exceptions=True)


async def test_advisory_lock_wait_returns_on_server_visible_wait() -> None:
    task = asyncio.create_task(asyncio.Event().wait())
    try:
        await wait_for_postgres_advisory_lock_wait(
            task,
            _ObserverSessionFactory(True),
            backend_pid=1729,
            timeout=1,
        )
    finally:
        await cancel_pending_tasks(task)


async def test_advisory_lock_wait_bounds_stalled_observer_query() -> None:
    async def stalled_query() -> bool:
        await asyncio.Event().wait()
        return False

    task = asyncio.create_task(asyncio.Event().wait())
    with pytest.raises(TimeoutError, match="observation exceeded"):
        await wait_for_postgres_advisory_lock_wait(
            task,
            _ObserverSessionFactory(stalled_query),
            backend_pid=1729,
            timeout=0.01,
        )
    await cancel_pending_tasks(task)


async def test_advisory_lock_wait_does_not_block_on_stalled_cancellation_cleanup() -> None:
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def cancellation_stalled_query() -> bool:
        try:
            await asyncio.Event().wait()
            raise AssertionError("unreachable stalled query completion")
        except asyncio.CancelledError:
            await release_cleanup.wait()
            raise
        finally:
            cleanup_finished.set()

    task = asyncio.create_task(asyncio.Event().wait())
    with pytest.raises(TimeoutError, match="observation exceeded"):
        await asyncio.wait_for(
            wait_for_postgres_advisory_lock_wait(
                task,
                _ObserverSessionFactory(cancellation_stalled_query),
                backend_pid=1729,
                timeout=0.01,
            ),
            timeout=0.1,
        )

    release_cleanup.set()
    await asyncio.wait_for(cleanup_finished.wait(), timeout=0.1)
    await cancel_pending_tasks(task)


async def test_advisory_lock_wait_propagates_contender_failure_during_observation() -> None:
    async def stalled_query() -> bool:
        await asyncio.Event().wait()
        return False

    async def failed_contender() -> None:
        await asyncio.sleep(0)
        raise ConnectionError("contender connection failed")

    task = asyncio.create_task(failed_contender())
    with pytest.raises(ConnectionError, match="contender connection failed"):
        await wait_for_postgres_advisory_lock_wait(
            task,
            _ObserverSessionFactory(stalled_query),
            backend_pid=1729,
            timeout=1,
        )
    await cancel_pending_tasks(task)
