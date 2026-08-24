from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.release.build_runtime_image_set import (
    REPO_ROOT,
    build_runtime_image_set,
)


def _environment() -> dict[str, str]:
    return {
        "PATH": "test-path",
        "LOTUS_RUNTIME_IMAGE_SET_GROUP": "pr-runtime-image-set",
        "LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA": "a" * 40,
        "LOTUS_RUNTIME_IMAGE_SET_SOURCE_BRANCH": "feat/governed-checks",
        "LOTUS_RUNTIME_IMAGE_SET_REPOSITORY_URL": "https://github.com/sgajbi/lotus-core",
        "LOTUS_RUNTIME_IMAGE_SET_CI_RUN_ID": "12345",
    }


def test_build_runtime_image_set_runs_build_then_packaging_with_one_timestamp() -> None:
    calls: list[tuple[tuple[str, ...], Path, bool, dict[str, str]]] = []

    def runner(
        command: tuple[str, ...],
        *,
        cwd: Path,
        check: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, check, env))
        return subprocess.CompletedProcess(command, 0)

    build_runtime_image_set(
        environment=_environment(),
        generated_at_utc="2026-08-24T02:00:00Z",
        runner=runner,
    )

    assert len(calls) == 2
    build, package = calls
    assert build[0][1:] == (
        "scripts/release/prebuild_ci_images.py",
        "--cache-dir",
        ".buildx-cache",
        "--group",
        "pr-runtime-image-set",
        "--metrics-output",
        "output/runtime-image-set/build-metrics.json",
    )
    assert package[0][1:] == (
        "scripts/release/runtime_image_set.py",
        "create",
        "--group",
        "pr-runtime-image-set",
        "--manifest",
        "output/runtime-image-set/manifest.json",
        "--bundle",
        "output/runtime-image-set/images.tar",
        "--source-commit-sha",
        "a" * 40,
        "--source-branch",
        "feat/governed-checks",
        "--repository-url",
        "https://github.com/sgajbi/lotus-core",
        "--ci-run-id",
        "12345",
        "--generated-at-utc",
        "2026-08-24T02:00:00Z",
    )
    assert all(cwd == REPO_ROOT and check for _, cwd, check, _ in calls)
    assert all(env["LOTUS_BUILD_TIMESTAMP"] == "2026-08-24T02:00:00Z" for *_, env in calls)


def test_build_runtime_image_set_rejects_missing_metadata_before_execution() -> None:
    called = False

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        raise AssertionError("runner must not execute")

    environment = _environment()
    environment["LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA"] = " "

    with pytest.raises(SystemExit, match="LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA"):
        build_runtime_image_set(
            environment=environment,
            generated_at_utc="2026-08-24T02:00:00Z",
            runner=runner,
        )

    assert called is False


def test_build_runtime_image_set_stops_when_the_image_build_fails() -> None:
    calls = 0

    def runner(
        command: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise subprocess.CalledProcessError(7, command)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        build_runtime_image_set(
            environment=_environment(),
            generated_at_utc="2026-08-24T02:00:00Z",
            runner=runner,
        )

    assert exc_info.value.returncode == 7
    assert calls == 1
