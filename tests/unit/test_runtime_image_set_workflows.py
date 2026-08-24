"""Workflow contracts for one exact-source runtime image set per CI run."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.release.runtime_image_set import RuntimeImageSetError
from scripts.release.verify_runtime_image_set import verify_runtime_image_set_for_current_source

REPO_ROOT = Path(__file__).resolve().parents[2]
PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-merge-gate.yml"
MAIN_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "main-releasability.yml"

PR_RUNTIME_CONSUMERS = (
    "e2e-smoke",
    "docker-smoke-contract",
    "lotus-core-validation-report",
    "latency-gate",
    "performance-load-gate",
    "derived-state-recovery-gate",
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
RUNTIME_CONTROL_TARGETS = (
    "lotus-core-validate",
    "test-derived-state-recovery-gate",
    "test-docker-smoke",
    "test-e2e-all",
    "test-e2e-smoke",
    "test-failure-recovery-gate",
    "test-fixed-income-book-cost-recovery-gate",
    "test-institutional-completion-gate",
    "test-latency-gate",
    "test-performance-load-gate",
    "test-performance-load-gate-full",
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
    build = next(
        step
        for step in _steps(producer)
        if step.get("name") == "Build exact-source runtime image set"
    )
    assert build["run"] == "make build-runtime-image-set"
    assert build["shell"] == "bash"
    assert build["env"]["LOTUS_RUNTIME_IMAGE_SET_GROUP"] == group  # type: ignore[index]
    assert build["env"]["LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA"] == "${{ github.sha }}"  # type: ignore[index]
    assert (
        build["env"]["LOTUS_RUNTIME_IMAGE_SET_REPOSITORY_URL"]
        == "${{ github.server_url }}/${{ github.repository }}"
    )  # type: ignore[index]
    assert build["env"]["LOTUS_RUNTIME_IMAGE_SET_CI_RUN_ID"] == "${{ github.run_id }}"  # type: ignore[index]
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
        assert "Load and verify runtime image set" not in _step_names(job)
        commands = _run_commands(job)
        assert "prebuild_ci_images.py" not in commands
        assert "make runtime-image-set-load-verify" not in commands
        assert "GITHUB_ENV" not in commands
        assert "LOTUS_RUNTIME_IMAGE_SET_VERIFIED" not in str(job)
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


def _assert_runtime_control_prerequisites(makefile: str) -> None:
    for target in RUNTIME_CONTROL_TARGETS:
        declaration = next(line for line in makefile.splitlines() if line.startswith(f"{target}:"))
        assert declaration.split()[1:] == ["runtime-image-set-load-verify"]


def test_runtime_control_targets_bind_verification_as_a_make_prerequisite() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    _assert_runtime_control_prerequisites(makefile)

    mutated = makefile.replace(
        "test-docker-smoke: runtime-image-set-load-verify",
        "test-docker-smoke:",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_runtime_control_prerequisites(mutated)


def _run_runtime_make_target(
    *arguments: str, working_directory: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    make_executable = shutil.which("make")
    if make_executable is None:
        pytest.fail("GNU Make is required to verify runtime image-set prerequisite behavior")
    return subprocess.run(
        [make_executable, "--file", str(REPO_ROOT / "Makefile"), *arguments],
        cwd=working_directory,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def test_local_runtime_control_without_an_image_set_builds_from_source(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("CI", None)
    environment.pop("GITHUB_SHA", None)

    dry_run = _run_runtime_make_target(
        "--dry-run",
        "test-docker-smoke",
        working_directory=tmp_path,
        environment=environment,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "docker_endpoint_smoke.py --build" in dry_run.stdout

    messages: list[str] = []
    assert not verify_runtime_image_set_for_current_source(
        environment=environment,
        workspace=tmp_path,
        output=messages.append,
    )
    assert messages == ["No runtime image set present; controls build from source."]
    assert not (tmp_path / "output/runtime-image-set/verified-source-sha").exists()


def test_explicit_false_ci_runtime_control_builds_from_source(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["CI"] = "false"
    environment.pop("GITHUB_SHA", None)

    dry_run = _run_runtime_make_target(
        "--dry-run",
        "test-docker-smoke",
        working_directory=tmp_path,
        environment=environment,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "docker_endpoint_smoke.py --build" in dry_run.stdout

    assert not verify_runtime_image_set_for_current_source(
        environment=environment,
        workspace=tmp_path,
        output=lambda _message: None,
    )


def test_ci_runtime_verification_requires_the_exact_github_sha(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["CI"] = "true"
    environment.pop("GITHUB_SHA", None)

    with pytest.raises(RuntimeImageSetError, match="GITHUB_SHA is required in CI"):
        verify_runtime_image_set_for_current_source(
            environment=environment,
            workspace=tmp_path,
        )


def test_runtime_image_set_make_target_delegates_to_one_fail_fast_control() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("build-runtime-image-set:\n", maxsplit=1)[1].split(
        "\ngenerate-runtime-sbom:", maxsplit=1
    )[0]

    assert target.strip() == "$(REPOSITORY_PYTHON) scripts/release/build_runtime_image_set.py"

    load_target = makefile.split("runtime-image-set-load-verify:\n", maxsplit=1)[1].split(
        "\nclean:", maxsplit=1
    )[0]
    assert load_target.strip() == (
        "$(REPOSITORY_PYTHON) scripts/release/verify_runtime_image_set.py"
    )


def test_verified_runtime_image_set_uses_prerequisites_not_workflow_assertions() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "\nRUNTIME_BUILD_ARGUMENT =" not in makefile
    assert "\nCERTIFICATION_RUNTIME_BUILD_ARGUMENT =" not in makefile
    assert "LOTUS_RUNTIME_IMAGE_SET_VERIFIED" not in makefile
    assert "CI_IS_TRUE := $(filter $(CI_TRUTHY_VALUES),$(strip $(CI)))" in makefile
    assert "LOCAL_RUNTIME_BUILD_ARGUMENT = $(if $(CI_IS_TRUE),,--build)" in makefile
    assert "LOCAL_CERTIFICATION_BUILD_ARGUMENT = $(if $(CI_IS_TRUE),,--runtime-build)" in makefile
    for command in (
        "scripts/validation/docker_endpoint_smoke.py",
        "scripts/operations/latency_profile.py $(LOCAL_RUNTIME_BUILD_ARGUMENT) --enforce",
        "scripts/operations/performance_load_gate.py $(LOCAL_RUNTIME_BUILD_ARGUMENT) "
        "--profile-tier fast --enforce",
        "scripts/operations/failure_recovery_gate.py $(LOCAL_RUNTIME_BUILD_ARGUMENT) --enforce",
        "scripts.operations.recovery.derived_state_gate $(LOCAL_RUNTIME_BUILD_ARGUMENT) --enforce",
        "scripts/validation/certify_lotus_core_app.py",
    ):
        assert command in makefile


def test_managed_compose_gates_upload_project_owned_diagnostics() -> None:
    expected_jobs = {
        PR_WORKFLOW: {
            "e2e-smoke": "output/e2e-smoke/*",
            "docker-smoke-contract": "output/task-runs/diagnostics/docker-smoke-compose.log",
            "lotus-core-validation-report": "output/task-runs/diagnostics/*.log",
            "latency-gate": "output/task-runs/diagnostics/latency-gate-compose.log",
            "performance-load-gate": (
                "output/task-runs/diagnostics/performance-load-gate-compose.log"
            ),
            "derived-state-recovery-gate": (
                "output/task-runs/diagnostics/derived-state-recovery-gate-compose.log"
            ),
        },
        MAIN_WORKFLOW: {
            "docker-smoke-contract": "output/task-runs/diagnostics/docker-smoke-compose.log",
            "latency-gate": "output/task-runs/diagnostics/latency-gate-compose.log",
            "performance-load-gate": (
                "output/task-runs/diagnostics/performance-load-gate-compose.log"
            ),
            "integration-all": "output/integration-all/integration-all-compose.log",
            "e2e-all": "output/e2e-all/e2e-all-compose.log",
            "performance-load-gate-full": (
                "output/task-runs/diagnostics/performance-load-gate-compose.log"
            ),
            "failure-recovery-gate": (
                "output/task-runs/diagnostics/failure-recovery-gate-compose.log"
            ),
            "institutional-completion-gate": (
                "output/task-runs/diagnostics/institutional-completion-compose.log"
            ),
        },
    }

    for workflow_path, job_paths in expected_jobs.items():
        jobs = _workflow(workflow_path)["jobs"]
        for job_name, diagnostic_path in job_paths.items():
            job = jobs[job_name]  # type: ignore[index]
            assert "Capture docker compose logs on failure" not in _step_names(job)
            assert "docker compose logs" not in _run_commands(job)
            upload_paths = "\n".join(
                str(step.get("with", {}).get("path", ""))
                for step in _steps(job)
                if str(step.get("uses", "")).startswith("actions/upload-artifact@")
            )
            assert diagnostic_path in upload_paths


def test_main_failure_recovery_job_proves_both_runtime_boundaries() -> None:
    jobs = _workflow(MAIN_WORKFLOW)["jobs"]
    recovery_job = jobs["failure-recovery-gate"]  # type: ignore[index]
    commands = _run_commands(recovery_job)

    assert "make test-failure-recovery-gate" in commands
    assert "make test-derived-state-recovery-gate" in commands
    assert "output/task-runs/*derived-state-recovery-gate*.json" in str(
        next(
            step
            for step in _steps(recovery_job)
            if step.get("name") == "Upload failure recovery artifacts"
        )["with"]["path"]  # type: ignore[index]
    )
