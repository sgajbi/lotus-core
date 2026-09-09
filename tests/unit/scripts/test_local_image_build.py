from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.release.local_image_build import (
    LOCAL_CI_RUN_ID,
    LOCAL_IMAGE_DIGEST,
    LocalBuildMetadata,
    compose_up_command,
    discover_local_build_metadata,
    docker_build_command,
    run_local_build,
)


def _write_project(root: Path) -> None:
    root.joinpath("pyproject.toml").write_text(
        '[project]\nname = "lotus-core"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    root.joinpath(".dockerignore").write_text(".cache\n", encoding="utf-8")
    root.joinpath(".gitignore").write_text(".cache\n", encoding="utf-8")


def _run_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_metadata_matches_real_git_head_and_dirty_state(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", "pyproject.toml", ".dockerignore", ".gitignore")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")

    clean_metadata = discover_local_build_metadata(tmp_path)

    assert clean_metadata.git_commit_sha == expected_head
    tmp_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "lotus-core"\nversion = "0.1.1"\n', encoding="utf-8"
    )
    dirty_metadata = discover_local_build_metadata(tmp_path)
    assert dirty_metadata.git_commit_sha == f"{expected_head}-dirty"


def test_metadata_detects_untracked_files_when_git_config_hides_them(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", "pyproject.toml", ".dockerignore", ".gitignore")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    _run_git(tmp_path, "config", "status.showUntrackedFiles", "no")
    tmp_path.joinpath("untracked-source.py").write_text("value = 1\n", encoding="utf-8")

    assert _run_git(tmp_path, "status", "--porcelain") == ""
    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == f"{expected_head}-dirty"


@pytest.mark.skipif(os.name == "nt", reason="Windows worktrees do not expose POSIX mode changes")
def test_metadata_detects_mode_change_when_git_config_hides_it(tmp_path: Path) -> None:
    _write_project(tmp_path)
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", "pyproject.toml", ".dockerignore", ".gitignore", "source.py")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    _run_git(tmp_path, "config", "core.fileMode", "false")
    source.chmod(source.stat().st_mode | 0o111)

    assert _run_git(tmp_path, "status", "--porcelain") == ""
    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == f"{expected_head}-dirty"


@pytest.mark.parametrize("index_flag", ("--assume-unchanged", "--skip-worktree"))
def test_metadata_fails_closed_for_hidden_index_flags(tmp_path: Path, index_flag: str) -> None:
    _write_project(tmp_path)
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", "pyproject.toml", ".dockerignore", ".gitignore")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    _run_git(tmp_path, "update-index", index_flag, "pyproject.toml")
    tmp_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "lotus-core"\nversion = "0.1.1"\n', encoding="utf-8"
    )

    assert _run_git(tmp_path, "status", "--porcelain") == ""
    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == f"{expected_head}-dirty"


def test_metadata_detects_ignored_files_in_docker_context(tmp_path: Path) -> None:
    _write_project(tmp_path)
    app = tmp_path / "src" / "services" / "query_service" / "app"
    app.mkdir(parents=True)
    app.joinpath("main.py").write_text("value = 1\n", encoding="utf-8")
    dockerfile = app.parent / "Dockerfile"
    dockerfile.write_text(
        "FROM scratch\nCOPY src/services/query_service/app /app\n", encoding="utf-8"
    )
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    tmp_path.joinpath(".git", "info", "exclude").write_text(
        "src/services/query_service/app/ignored-source.py\n", encoding="utf-8"
    )
    app.joinpath("ignored-source.py").write_text("value = 1\n", encoding="utf-8")

    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == f"{expected_head}-dirty"


def test_metadata_ignores_ignored_file_outside_copied_sources(tmp_path: Path) -> None:
    _write_project(tmp_path)
    app = tmp_path / "src" / "services" / "query_service" / "app"
    app.mkdir(parents=True)
    app.joinpath("main.py").write_text("value = 1\n", encoding="utf-8")
    dockerfile = app.parent / "Dockerfile"
    dockerfile.write_text(
        "FROM scratch\nCOPY src/services/query_service/app /app\n", encoding="utf-8"
    )
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    tmp_path.joinpath(".git", "info", "exclude").write_text(
        ".import_linter_cache\n", encoding="utf-8"
    )
    tmp_path.joinpath(".import_linter_cache").write_text("local\n", encoding="utf-8")

    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == expected_head


def test_metadata_detects_untracked_empty_directory_in_copied_source(tmp_path: Path) -> None:
    _write_project(tmp_path)
    app = tmp_path / "src" / "services" / "query_service" / "app"
    app.mkdir(parents=True)
    app.joinpath("main.py").write_text("value = 1\n", encoding="utf-8")
    dockerfile = app.parent / "Dockerfile"
    dockerfile.write_text(
        "FROM scratch\nCOPY src/services/query_service/app /app\n", encoding="utf-8"
    )
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    app.joinpath("empty-extension").mkdir()

    assert _run_git(tmp_path, "status", "--porcelain") == ""
    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == f"{expected_head}-dirty"


def test_metadata_ignores_empty_directory_excluded_from_docker_context(tmp_path: Path) -> None:
    _write_project(tmp_path)
    app = tmp_path / "src" / "services" / "query_service" / "app"
    app.mkdir(parents=True)
    app.joinpath("main.py").write_text("value = 1\n", encoding="utf-8")
    dockerfile = app.parent / "Dockerfile"
    dockerfile.write_text(
        "FROM scratch\nCOPY src/services/query_service/app /app\n", encoding="utf-8"
    )
    tmp_path.joinpath(".dockerignore").write_text("**/empty-cache\n", encoding="utf-8")
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", ".")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    app.joinpath("empty-cache").mkdir()

    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == expected_head


def test_metadata_ignores_local_artifacts_excluded_from_docker_context(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    _run_git(tmp_path, "init", "--initial-branch", "main")
    _run_git(tmp_path, "config", "user.name", "Local Build Test")
    _run_git(tmp_path, "config", "user.email", "local-build@example.test")
    _run_git(tmp_path, "add", "pyproject.toml", ".dockerignore", ".gitignore")
    _run_git(tmp_path, "commit", "-m", "test fixture")
    expected_head = _run_git(tmp_path, "rev-parse", "HEAD")
    cache = tmp_path / ".cache"
    cache.mkdir()
    cache.joinpath("state.json").write_text("{}\n", encoding="utf-8")

    metadata = discover_local_build_metadata(tmp_path)

    assert metadata.git_commit_sha == expected_head


def test_discovers_exact_clean_checkout_provenance(tmp_path: Path) -> None:
    _write_project(tmp_path)
    outputs = iter(
        (
            "a" * 40 + "\n",
            "fix/1107-local-image-provenance\n",
            "",
            "",
            "",
            "",
        )
    )

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=next(outputs), stderr="")

    metadata = discover_local_build_metadata(
        tmp_path,
        runner=runner,
        now=lambda: datetime(2026, 9, 9, 1, 2, 3, tzinfo=UTC),
    )

    assert metadata.git_commit_sha == "a" * 40
    assert metadata.git_branch == "fix/1107-local-image-provenance"
    assert metadata.build_timestamp == "2026-09-09T01:02:03Z"
    assert metadata.repo_url == "https://github.com/sgajbi/lotus-core"
    assert metadata.image_version == "0.1.0-local.aaaaaaaaaaaa"
    assert metadata.image_digest == LOCAL_IMAGE_DIGEST
    assert metadata.ci_run_id == LOCAL_CI_RUN_ID


def test_marks_modified_checkout_without_reinterpreting_branch_text(tmp_path: Path) -> None:
    _write_project(tmp_path)
    hostile_branch = "fix/quoted-'; echo not-code; '$value"
    outputs = iter(("b" * 40, hostile_branch, " M Makefile"))
    commands: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=next(outputs), stderr="")

    metadata = discover_local_build_metadata(tmp_path, runner=runner)
    command = docker_build_command(metadata)

    assert metadata.git_commit_sha == f"{'b' * 40}-dirty"
    assert metadata.git_branch == hostile_branch
    assert f"LOTUS_GIT_BRANCH={hostile_branch}" in command
    assert all(isinstance(command, list) for command in commands)


def test_runs_compose_with_metadata_in_environment_and_without_shell() -> None:
    captured: dict[str, object] = {}

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    build_metadata = LocalBuildMetadata(
        git_commit_sha="sha",
        git_branch="branch",
        build_timestamp="timestamp",
        repo_url="repo",
        image_version="version",
    )
    command = compose_up_command(("query_control_plane_service",), no_deps=True)
    run_local_build(command, build_metadata, runner=runner)

    assert captured["command"] == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "up",
        "--detach",
        "--build",
        "--no-deps",
        "query_control_plane_service",
    ]
    assert captured["check"] is True
    assert captured["env"]["LOTUS_GIT_COMMIT_SHA"] == "sha"  # type: ignore[index]
    assert "shell" not in captured
