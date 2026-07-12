"""Workflow contracts for one exact-source runtime image set per CI run."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-merge-gate.yml"
MAIN_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "main-releasability.yml"

PR_RUNTIME_CONSUMERS = (
    "e2e-smoke",
    "docker-smoke-contract",
    "lotus-core-validation-report",
    "latency-gate",
    "performance-load-gate",
)
MAIN_RUNTIME_CONSUMERS = (
    "docker-smoke-contract",
    "latency-gate",
    "performance-load-gate",
    "e2e-all",
    "performance-load-gate-full",
    "failure-recovery-gate",
    "institutional-completion-gate",
)


def _workflow(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    return job["steps"]  # type: ignore[return-value]


def _step_names(job: dict[str, object]) -> set[str]:
    return {str(step.get("name", "")) for step in _steps(job)}


def _run_commands(job: dict[str, object]) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(job))


def _assert_runtime_image_producer(
    workflow: dict[str, object],
    *,
    group: str,
    artifact_name: str,
) -> None:
    jobs = workflow["jobs"]
    producer = jobs["docker-build"]  # type: ignore[index]
    commands = _run_commands(producer)
    assert f"prebuild_ci_images.py --cache-dir .buildx-cache --group {group}" in commands
    assert "--metrics-output output/runtime-image-set/build-metrics.json" in commands
    assert "runtime_image_set.py create" in commands
    assert '--source-commit-sha "${GITHUB_SHA}"' in commands
    upload = next(
        step for step in _steps(producer) if step.get("name") == "Upload runtime image set"
    )
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["name"] == artifact_name  # type: ignore[index]
    assert upload["with"]["if-no-files-found"] == "error"  # type: ignore[index]


def _assert_runtime_image_consumers(
    workflow: dict[str, object],
    *,
    consumers: tuple[str, ...],
    artifact_name: str,
) -> None:
    jobs = workflow["jobs"]  # type: ignore[assignment]
    for job_name in consumers:
        job = jobs[job_name]  # type: ignore[index]
        needs = job["needs"]
        assert "docker-build" in ([needs] if isinstance(needs, str) else needs)
        assert "Download runtime image set" in _step_names(job)
        assert "Load and verify runtime image set" in _step_names(job)
        commands = _run_commands(job)
        assert "prebuild_ci_images.py" not in commands
        assert "runtime_image_set.py load-verify" in commands
        assert '--expected-commit-sha "${GITHUB_SHA}"' in commands
        download = next(
            step for step in _steps(job) if step.get("name") == "Download runtime image set"
        )
        assert download["uses"] == "actions/download-artifact@v8"
        assert download["with"]["name"] == artifact_name  # type: ignore[index]


def test_pr_workflow_builds_and_consumes_one_exact_source_runtime_image_set() -> None:
    workflow = _workflow(PR_WORKFLOW)

    _assert_runtime_image_producer(
        workflow,
        group="pr-runtime-image-set",
        artifact_name="pr-runtime-image-set",
    )
    _assert_runtime_image_consumers(
        workflow,
        consumers=PR_RUNTIME_CONSUMERS,
        artifact_name="pr-runtime-image-set",
    )


def test_main_workflow_builds_and_consumes_one_exact_source_runtime_image_set() -> None:
    workflow = _workflow(MAIN_WORKFLOW)

    _assert_runtime_image_producer(
        workflow,
        group="main-runtime-image-set",
        artifact_name="main-runtime-image-set",
    )
    _assert_runtime_image_consumers(
        workflow,
        consumers=MAIN_RUNTIME_CONSUMERS,
        artifact_name="main-runtime-image-set",
    )


def test_verified_runtime_image_set_disables_repo_image_rebuild_flags() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "RUNTIME_BUILD_ARGUMENT = $(if $(filter true,$(CI)),,--build)" in makefile
    assert (
        "CERTIFICATION_RUNTIME_BUILD_ARGUMENT = "
        "$(if $(filter true,$(CI)),,--runtime-build)" in makefile
    )
    for command in (
        "docker_endpoint_smoke.py $(RUNTIME_BUILD_ARGUMENT)",
        "latency_profile.py $(RUNTIME_BUILD_ARGUMENT)",
        "performance_load_gate.py $(RUNTIME_BUILD_ARGUMENT)",
        "failure_recovery_gate.py $(RUNTIME_BUILD_ARGUMENT)",
        "certify_lotus_core_app.py $(CERTIFICATION_RUNTIME_BUILD_ARGUMENT)",
    ):
        assert command in makefile
