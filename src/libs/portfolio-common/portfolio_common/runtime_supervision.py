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
    for consumer in consumers:
        shutdown = getattr(consumer, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                if logger is not None:
                    logger.error(
                        "Consumer shutdown callback failed during runtime teardown.",
                        exc_info=True,
                    )

    for stop_callback in stop_callbacks:
        try:
            stop_callback()
        except Exception:
            if logger is not None:
                logger.error(
                    "Runtime stop callback failed during teardown.",
                    exc_info=True,
                )

    if server is not None:
        server.should_exit = True

    if not tasks:
        return

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=shutdown_timeout_seconds,
        )
    except asyncio.TimeoutError:
        timed_out_task_names = [
            task.get_name() or "unnamed-task"
            for task in tasks
            if not task.done() or task.cancelled()
        ]
        if logger is not None:
            logger.error(
                "Runtime teardown timed out; force-cancelling remaining tasks.",
                extra={"timed_out_tasks": timed_out_task_names},
            )
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
