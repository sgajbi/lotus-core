from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Sequence

WORKER_RUNTIME_DEPENDENCY = "worker_runtime"
WORKER_RUNTIME_HEALTH_NAME = "worker_runtime"


@dataclass(frozen=True)
class WorkerRuntimeReadinessSnapshot:
    service_name: str
    status: str
    active_task_count: int
    failed_task_names: tuple[str, ...] = ()

    @property
    def is_ready(self) -> bool:
        return self.status == "ok"


_WORKER_RUNTIME_TASKS: dict[str, tuple[asyncio.Task, ...]] = {}
_WORKER_RUNTIME_STOPPING: set[str] = set()
_WORKER_RUNTIME_FAILED: dict[str, tuple[str, ...]] = {}


def register_worker_runtime_tasks(
    *,
    service_name: str,
    tasks: Sequence[asyncio.Task],
) -> None:
    _WORKER_RUNTIME_TASKS[service_name] = tuple(tasks)
    _WORKER_RUNTIME_STOPPING.discard(service_name)
    _WORKER_RUNTIME_FAILED.pop(service_name, None)


def mark_worker_runtime_stopping(*, service_name: str) -> None:
    _WORKER_RUNTIME_STOPPING.add(service_name)


def mark_worker_runtime_failed(
    *,
    service_name: str,
    task_names: Sequence[str],
) -> None:
    _WORKER_RUNTIME_FAILED[service_name] = tuple(
        _bounded_task_name(task_name) for task_name in task_names if task_name
    ) or ("unnamed-task",)


def clear_worker_runtime_readiness(*, service_name: str) -> None:
    _WORKER_RUNTIME_TASKS.pop(service_name, None)
    _WORKER_RUNTIME_STOPPING.discard(service_name)
    _WORKER_RUNTIME_FAILED.pop(service_name, None)


def worker_runtime_configured(*, service_name: str) -> bool:
    return service_name in _WORKER_RUNTIME_TASKS


async def check_worker_runtime_health_status(*, service_name: str) -> str:
    return worker_runtime_readiness_snapshot(service_name=service_name).status


def worker_runtime_readiness_snapshot(*, service_name: str) -> WorkerRuntimeReadinessSnapshot:
    tasks = _WORKER_RUNTIME_TASKS.get(service_name)
    if tasks is None:
        return WorkerRuntimeReadinessSnapshot(
            service_name=service_name,
            status="misconfigured",
            active_task_count=0,
        )
    if service_name in _WORKER_RUNTIME_STOPPING:
        return WorkerRuntimeReadinessSnapshot(
            service_name=service_name,
            status="stopping",
            active_task_count=_active_task_count(tasks),
        )
    failed_task_names = _WORKER_RUNTIME_FAILED.get(service_name) or tuple(
        _bounded_task_name(task.get_name() or "unnamed-task") for task in tasks if task.done()
    )
    if failed_task_names:
        return WorkerRuntimeReadinessSnapshot(
            service_name=service_name,
            status="failed",
            active_task_count=_active_task_count(tasks),
            failed_task_names=tuple(failed_task_names),
        )
    if not tasks:
        return WorkerRuntimeReadinessSnapshot(
            service_name=service_name,
            status="misconfigured",
            active_task_count=0,
        )
    return WorkerRuntimeReadinessSnapshot(
        service_name=service_name,
        status="ok",
        active_task_count=_active_task_count(tasks),
    )


def _active_task_count(tasks: Sequence[asyncio.Task]) -> int:
    return sum(1 for task in tasks if not task.done())


def _bounded_task_name(task_name: str) -> str:
    sanitized = "".join(character if character.isprintable() else "_" for character in task_name)
    return (sanitized.strip() or "unnamed-task")[:128]
