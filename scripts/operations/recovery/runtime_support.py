"""Control one Compose runtime interruption and measure Kafka backlog growth."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Protocol


class KafkaPartitionOffset(Protocol):
    """Expose the offset values required to calculate one partition's lag."""

    high_watermark: int
    committed_offset: int


class KafkaOffsetSnapshot(Protocol):
    """Expose partition offsets for one consumer-group topic snapshot."""

    partitions: tuple[KafkaPartitionOffset, ...]


class KafkaOffsetReader(Protocol):
    """Read one consumer group's offsets without binding to a Kafka client."""

    def snapshot(self, *, group_id: str, topic: str) -> KafkaOffsetSnapshot: ...


def run_capture(command: list[str], *, cwd: Path) -> str:
    """Run one operator command and return stdout or fail with full diagnostics."""

    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed.stdout


def compose_command(
    *, compose_file: str, compose_project_name: str | None, arguments: list[str]
) -> list[str]:
    """Build a Compose command scoped to an optional evidence project."""

    command = ["docker", "compose"]
    if compose_project_name:
        command.extend(["-p", compose_project_name])
    command.extend(["-f", compose_file, *arguments])
    return command


def resolve_interruption_container(
    *,
    repo_root: Path,
    compose_file: str,
    compose_project_name: str | None,
    interruption_service: str,
) -> str:
    """Resolve one running Compose service to the exact container that will be interrupted."""

    target = interruption_service.strip()
    if not target:
        raise ValueError("interruption service cannot be empty")
    container_id = run_capture(
        compose_command(
            compose_file=compose_file,
            compose_project_name=compose_project_name,
            arguments=["ps", "-q", target],
        ),
        cwd=repo_root,
    ).strip()
    if not container_id:
        raise RuntimeError(f"Compose service is not running: {target}")
    return container_id


def set_container_pause(*, container_id: str, paused: bool, repo_root: Path) -> None:
    """Pause or resume the exact container resolved for an interruption proof."""

    operation = "pause" if paused else "unpause"
    run_capture(["docker", operation, container_id], cwd=repo_root)


def consumer_lag(*, store: KafkaOffsetReader, consumer_group: str, topic: str) -> int:
    """Return non-negative total lag, treating an uncommitted partition as offset zero."""

    snapshot = store.snapshot(group_id=consumer_group, topic=topic)
    return sum(
        max(partition.high_watermark - max(partition.committed_offset, 0), 0)
        for partition in snapshot.partitions
    )


def wait_for_lag_growth(
    *,
    store: KafkaOffsetReader,
    consumer_group: str,
    topic: str,
    baseline_lag: int,
    expected_growth: int,
    timeout_seconds: int,
) -> int:
    """Return once lag grows by the required amount or the bounded wait expires."""

    peak_lag = baseline_lag
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        current_lag = consumer_lag(
            store=store,
            consumer_group=consumer_group,
            topic=topic,
        )
        peak_lag = max(peak_lag, current_lag)
        if peak_lag - baseline_lag >= expected_growth:
            return peak_lag
        time.sleep(1)
    return peak_lag
