import asyncio
import logging
from unittest.mock import patch

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


async def test_prefers_real_failure_over_simultaneous_cancelled_task():
    shutdown_event = asyncio.Event()
    logger = logging.getLogger("test-runtime-supervision")

    started = asyncio.Event()

    async def _failing():
        await started.wait()
        raise ValueError("boom")

    async def _cancelled():
        await started.wait()
        raise asyncio.CancelledError

    failing_task = asyncio.create_task(_failing(), name="failing-task")
    cancelled_task = asyncio.create_task(_cancelled(), name="cancelled-task")
    await asyncio.sleep(0)
    started.set()
    await asyncio.sleep(0)

    result = await wait_for_shutdown_or_task_failure(
        tasks=[cancelled_task, failing_task],
        shutdown_event=shutdown_event,
        logger=logger,
    )

    assert isinstance(result, RuntimeError)
    assert "Critical service task 'failing-task' failed." in str(result)
    assert isinstance(result.__cause__, ValueError)


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
    cancelled = asyncio.Event()

    async def _stuck_task():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(_stuck_task(), name="stuck-task")

    await shutdown_runtime_components(
        tasks=[task],
        shutdown_timeout_seconds=0.01,
    )

    assert task.cancelled() is True
    assert cancelled.is_set() is True


async def test_shutdown_runtime_components_continues_after_callback_failures():
    logger = logging.getLogger("test-runtime-supervision")
    stop_marker: list[str] = []

    class _FailingConsumer:
        def shutdown(self) -> None:
            stop_marker.append("consumer")
            raise RuntimeError("consumer shutdown failed")

    class _HealthyConsumer:
        def __init__(self) -> None:
            self.shutdown_called = False

        def shutdown(self) -> None:
            self.shutdown_called = True
            stop_marker.append("healthy-consumer")

    stop_event = asyncio.Event()

    async def _task():
        await stop_event.wait()

    task = asyncio.create_task(_task(), name="managed-task")
    healthy_consumer = _HealthyConsumer()

    def _failing_stop_callback() -> None:
        stop_marker.append("callback")
        raise RuntimeError("stop callback failed")

    def _healthy_stop_callback() -> None:
        stop_marker.append("healthy-callback")
        stop_event.set()

    with patch.object(logger, "error") as mock_log_error:
        await shutdown_runtime_components(
            tasks=[task],
            consumers=[_FailingConsumer(), healthy_consumer],
            stop_callbacks=[_failing_stop_callback, _healthy_stop_callback],
            logger=logger,
        )

    assert healthy_consumer.shutdown_called is True
    assert stop_marker == ["consumer", "healthy-consumer", "callback", "healthy-callback"]
    assert mock_log_error.call_count == 2


async def test_shutdown_runtime_components_logs_timed_out_task_names():
    logger = logging.getLogger("test-runtime-supervision")

    async def _stuck_task():
        await asyncio.Future()

    task = asyncio.create_task(_stuck_task(), name="stuck-task")

    with patch.object(logger, "error") as mock_log_error:
        await shutdown_runtime_components(
            tasks=[task],
            shutdown_timeout_seconds=0.01,
            logger=logger,
        )

    assert task.cancelled() is True
    assert mock_log_error.call_args.kwargs["extra"]["timed_out_tasks"] == ["stuck-task"]
