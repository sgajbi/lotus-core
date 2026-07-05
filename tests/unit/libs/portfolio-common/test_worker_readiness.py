import asyncio

import pytest
from portfolio_common.worker_readiness import (
    check_worker_runtime_health_status,
    clear_worker_runtime_readiness,
    mark_worker_runtime_failed,
    mark_worker_runtime_stopping,
    register_worker_runtime_tasks,
    worker_runtime_configured,
    worker_runtime_readiness_snapshot,
)

pytestmark = pytest.mark.asyncio


async def _wait_forever() -> None:
    await asyncio.Future()


async def test_worker_runtime_readiness_reports_active_tasks_ready() -> None:
    task = asyncio.create_task(_wait_forever(), name="consumer-task")
    service_name = "worker_service_web"
    try:
        register_worker_runtime_tasks(service_name=service_name, tasks=[task])

        snapshot = worker_runtime_readiness_snapshot(service_name=service_name)

        assert worker_runtime_configured(service_name=service_name) is True
        assert snapshot.status == "ok"
        assert snapshot.active_task_count == 1
        assert await check_worker_runtime_health_status(service_name=service_name) == "ok"
    finally:
        clear_worker_runtime_readiness(service_name=service_name)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_worker_runtime_readiness_reports_unregistered_service_as_misconfigured() -> None:
    service_name = "missing_worker_service_web"

    snapshot = worker_runtime_readiness_snapshot(service_name=service_name)

    assert worker_runtime_configured(service_name=service_name) is False
    assert snapshot.status == "misconfigured"
    assert snapshot.is_ready is False


async def test_worker_runtime_readiness_reports_completed_task_as_failed() -> None:
    async def _exits() -> None:
        return None

    task = asyncio.create_task(_exits(), name="consumer-exited")
    service_name = "failed_worker_service_web"
    await task
    try:
        register_worker_runtime_tasks(service_name=service_name, tasks=[task])

        snapshot = worker_runtime_readiness_snapshot(service_name=service_name)

        assert snapshot.status == "failed"
        assert snapshot.active_task_count == 0
        assert snapshot.failed_task_names == ("consumer-exited",)
    finally:
        clear_worker_runtime_readiness(service_name=service_name)


async def test_worker_runtime_readiness_reports_explicit_failed_and_stopping_states() -> None:
    task = asyncio.create_task(_wait_forever(), name="consumer-task")
    service_name = "stateful_worker_service_web"
    try:
        register_worker_runtime_tasks(service_name=service_name, tasks=[task])
        mark_worker_runtime_failed(service_name=service_name, task_names=["dlq-dispatcher"])

        failed_snapshot = worker_runtime_readiness_snapshot(service_name=service_name)

        assert failed_snapshot.status == "failed"
        assert failed_snapshot.failed_task_names == ("dlq-dispatcher",)

        mark_worker_runtime_stopping(service_name=service_name)

        stopping_snapshot = worker_runtime_readiness_snapshot(service_name=service_name)

        assert stopping_snapshot.status == "stopping"
        assert stopping_snapshot.is_ready is False
    finally:
        clear_worker_runtime_readiness(service_name=service_name)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
