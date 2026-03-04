from pathlib import Path

import pytest

from scripts.failure_recovery_gate import (
    _pause_container,
    _resolve_interruption_container,
    _unpause_container,
)


def test_resolve_interruption_container_prefers_compose_resolved_container_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "abc123containerid\n",
    )

    resolved = _resolve_interruption_container(
        repo_root=Path("."),
        compose_file="docker-compose.yml",
        interruption_container="persistence_service",
    )

    assert resolved == "abc123containerid"


def test_resolve_interruption_container_falls_back_to_raw_input_when_service_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.failure_recovery_gate._run_capture",
        lambda cmd, cwd: "",
    )

    resolved = _resolve_interruption_container(
        repo_root=Path("."),
        compose_file="docker-compose.yml",
        interruption_container="persistence_service",
    )

    assert resolved == "persistence_service"


def test_resolve_interruption_container_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        _resolve_interruption_container(
            repo_root=Path("."),
            compose_file="docker-compose.yml",
            interruption_container=" ",
        )


def test_pause_and_unpause_use_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(cmd: list[str], cwd: Path) -> None:
        calls.append((cmd, cwd))

    monkeypatch.setattr("scripts.failure_recovery_gate._run", _fake_run)

    repo_root = Path("/tmp/repo")
    _pause_container("container-id", repo_root=repo_root)
    _unpause_container("container-id", repo_root=repo_root)

    assert calls == [
        (["docker", "pause", "container-id"], repo_root),
        (["docker", "unpause", "container-id"], repo_root),
    ]
