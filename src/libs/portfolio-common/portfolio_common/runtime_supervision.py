import asyncio
import contextlib
from collections.abc import Callable, Sequence


async def wait_for_shutdown_or_task_failure(
    *,
    tasks: Sequence[asyncio.Task],
    shutdown_event: asyncio.Event,
    logger,
) -> RuntimeError | None:
    """
    Wait until an explicit shutdown signal arrives or a critical runtime task exits.

    Returns:
    - None when shutdown was explicitly requested.
    - RuntimeError when a critical task exited unexpectedly.
    """
    if not tasks:
        await shutdown_event.wait()
        return None

    shutdown_wait_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-wait")
    try:
        done, _ = await asyncio.wait(
            [*tasks, shutdown_wait_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if shutdown_wait_task in done:
            return None

        completed_tasks = [task for task in done if task is not shutdown_wait_task]
        failed_task = _select_failed_runtime_task(completed_tasks)
        runtime_error = _runtime_error_for_failed_task(failed_task)
        logger.error("Critical runtime task failure detected; initiating shutdown.")
        shutdown_event.set()
        return runtime_error
    finally:
        shutdown_wait_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await shutdown_wait_task


def _select_failed_runtime_task(tasks: Sequence[asyncio.Task]) -> asyncio.Task:
    exception_task = _find_exception_runtime_task(tasks)
    if exception_task is not None:
        return exception_task
    cancelled_task = _find_cancelled_runtime_task(tasks)
    if cancelled_task is not None:
        return cancelled_task
    return tasks[0]


def _find_exception_runtime_task(tasks: Sequence[asyncio.Task]) -> asyncio.Task | None:
    return next(
        (task for task in tasks if not task.cancelled() and task.exception() is not None),
        None,
    )


def _find_cancelled_runtime_task(tasks: Sequence[asyncio.Task]) -> asyncio.Task | None:
    return next((task for task in tasks if task.cancelled()), None)


def _runtime_error_for_failed_task(task: asyncio.Task) -> RuntimeError:
    task_name = task.get_name() or "unnamed-task"
    if task.cancelled():
        return RuntimeError(f"Critical service task '{task_name}' was cancelled unexpectedly.")
    task_error = task.exception()
    if task_error is None:
        return RuntimeError(f"Critical service task '{task_name}' exited unexpectedly.")
    runtime_error = RuntimeError(f"Critical service task '{task_name}' failed.")
    runtime_error.__cause__ = task_error
    return runtime_error


async def shutdown_runtime_components(
    *,
    tasks: Sequence[asyncio.Task],
    consumers: Sequence[object] = (),
    stop_callbacks: Sequence[Callable[[], object]] = (),
    server=None,
    shutdown_timeout_seconds: float = 10.0,
    logger=None,
) -> None:
    """
    Stop service-local runtime components and await task teardown.

    Consumers are shut down first, then service-local stop callbacks are invoked,
    then the embedded web server is asked to exit, and finally all runtime tasks
    are awaited with `return_exceptions=True` to guarantee bounded shutdown.
    """
    _shutdown_consumers(consumers, logger)
    _run_stop_callbacks(stop_callbacks, logger)
    _signal_server_exit(server)
    await _await_runtime_tasks(tasks, shutdown_timeout_seconds, logger)


def _shutdown_consumers(consumers: Sequence[object], logger) -> None:
    for consumer in consumers:
        _shutdown_consumer(consumer, logger)


def _shutdown_consumer(consumer: object, logger) -> None:
    shutdown = getattr(consumer, "shutdown", None)
    if not callable(shutdown):
        return
    try:
        shutdown()
    except Exception:
        _log_runtime_teardown_error(
            logger,
            "Consumer shutdown callback failed during runtime teardown.",
        )


def _run_stop_callbacks(stop_callbacks: Sequence[Callable[[], object]], logger) -> None:
    for stop_callback in stop_callbacks:
        _run_stop_callback(stop_callback, logger)


def _run_stop_callback(stop_callback: Callable[[], object], logger) -> None:
    try:
        stop_callback()
    except Exception:
        _log_runtime_teardown_error(
            logger,
            "Runtime stop callback failed during teardown.",
        )


def _signal_server_exit(server) -> None:
    if server is not None:
        server.should_exit = True


async def _await_runtime_tasks(
    tasks: Sequence[asyncio.Task],
    shutdown_timeout_seconds: float,
    logger,
) -> None:
    if not tasks:
        return

    try:
        await _gather_runtime_tasks(tasks, shutdown_timeout_seconds)
    except asyncio.TimeoutError:
        await _cancel_timed_out_runtime_tasks(tasks, logger)


async def _gather_runtime_tasks(
    tasks: Sequence[asyncio.Task],
    shutdown_timeout_seconds: float,
) -> None:
    await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=shutdown_timeout_seconds,
    )


async def _cancel_timed_out_runtime_tasks(
    tasks: Sequence[asyncio.Task],
    logger,
) -> None:
    _log_runtime_teardown_timeout(logger, _timed_out_task_names(tasks))
    _cancel_pending_runtime_tasks(tasks)
    await asyncio.gather(*tasks, return_exceptions=True)


def _log_runtime_teardown_timeout(logger, timed_out_task_names: list[str]) -> None:
    if logger is None:
        return
    logger.error(
        "Runtime teardown timed out; force-cancelling remaining tasks.",
        extra={"timed_out_tasks": timed_out_task_names},
    )


def _timed_out_task_names(tasks: Sequence[asyncio.Task]) -> list[str]:
    return [
        task.get_name() or "unnamed-task" for task in tasks if not task.done() or task.cancelled()
    ]


def _cancel_pending_runtime_tasks(tasks: Sequence[asyncio.Task]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()


def _log_runtime_teardown_error(logger, message: str) -> None:
    if logger is None:
        return
    logger.error(message, exc_info=True)
