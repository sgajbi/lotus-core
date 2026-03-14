import asyncio
import logging

import pytest
from portfolio_common.runtime_supervision import (
    shutdown_runtime_components,
    wait_for_shutdown_or_task_failure,
)

pytestmark = pytest.mark.asyncio


async def test_returns_none_on_explicit_shutdown():
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    logger = logging.getLogger("test-runtime-supervision")

    result = await wait_for_shutdown_or_task_failure(
        tasks=[],
        shutdown_event=shutdown_event,
        logger=logger,
    )

    assert result is None


async def test_returns_runtime_error_when_task_fails():
    shutdown_event = asyncio.Event()
    logger = logging.getLogger("test-runtime-supervision")

    async def _failing():
        raise ValueError("boom")

    failing_task = asyncio.create_task(_failing(), name="failing-task")
    result = await wait_for_shutdown_or_task_failure(
        tasks=[failing_task],
        shutdown_event=shutdown_event,
        logger=logger,
    )

    assert isinstance(result, RuntimeError)
    assert "Critical service task 'failing-task' failed." in str(result)
    assert isinstance(result.__cause__, ValueError)
    assert shutdown_event.is_set() is True


async def test_shutdown_runtime_components_stops_consumers_callbacks_and_server():
    stop_marker: list[str] = []

    class _FakeConsumer:
        def __init__(self) -> None:
            self.shutdown_called = False

        def shutdown(self) -> None:
            self.shutdown_called = True
            stop_marker.append("consumer")

    class _FakeServer:
        def __init__(self) -> None:
            self.should_exit = False

    stop_event = asyncio.Event()

    async def _task():
        await stop_event.wait()

    task = asyncio.create_task(_task(), name="managed-task")
    consumer = _FakeConsumer()
    server = _FakeServer()

    def _stop_callback() -> None:
        stop_marker.append("callback")
        stop_event.set()

    await shutdown_runtime_components(
        tasks=[task],
        consumers=[consumer],
        stop_callbacks=[_stop_callback],
        server=server,
    )

    assert consumer.shutdown_called is True
    assert server.should_exit is True
    assert stop_marker == ["consumer", "callback"]


async def test_shutdown_runtime_components_cancels_stuck_tasks_after_timeout():
    stop_event = asyncio.Event()
    cancelled = asyncio.Event()

    async def _stuck_task():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(_stuck_task(), name="stuck-task")

    def _stop_callback() -> None:
        stop_event.set()

    await shutdown_runtime_components(
        tasks=[task],
        stop_callbacks=[_stop_callback],
        shutdown_timeout_seconds=0.01,
    )

    assert task.cancelled() is True
    assert cancelled.is_set() is True
