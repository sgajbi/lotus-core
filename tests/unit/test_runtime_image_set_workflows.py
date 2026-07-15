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
        assert "LOTUS_RUNTIME_IMAGE_SET_VERIFIED=true" in commands
        assert '>> "${GITHUB_ENV}"' in commands
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

    assert (
        "RUNTIME_BUILD_ARGUMENT = "
        "$(if $(filter true,$(LOTUS_RUNTIME_IMAGE_SET_VERIFIED)),,--build)" in makefile
    )
    assert (
        "CERTIFICATION_RUNTIME_BUILD_ARGUMENT = "
        "$(if $(filter true,$(LOTUS_RUNTIME_IMAGE_SET_VERIFIED)),,--runtime-build)" in makefile
    )
    assert "$(filter true,$(CI))" not in makefile
    for command in (
        "docker_endpoint_smoke.py $(RUNTIME_BUILD_ARGUMENT)",
        "latency_profile.py $(RUNTIME_BUILD_ARGUMENT)",
        "performance_load_gate.py $(RUNTIME_BUILD_ARGUMENT)",
        "failure_recovery_gate.py $(RUNTIME_BUILD_ARGUMENT)",
        "scripts.operations.recovery.derived_state_gate $(RUNTIME_BUILD_ARGUMENT)",
        "certify_lotus_core_app.py $(CERTIFICATION_RUNTIME_BUILD_ARGUMENT)",
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
