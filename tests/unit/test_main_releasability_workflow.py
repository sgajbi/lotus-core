import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.quality.test_manifest import suite_pytest_command

WORKFLOW_PATH = Path(".github/workflows/main-releasability.yml")


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _needs(job: dict[str, object]) -> tuple[str, ...]:
    value = job.get("needs", ())
    if isinstance(value, str):
        return (value,)
    return tuple(value)  # type: ignore[arg-type]


def _assert_parallel_integration_admission(workflow: dict[str, object]) -> None:
    """Pin scheduling and default-success admission, not emulate hosted execution."""
    jobs = workflow["jobs"]
    expected_edges = {
        "exact-revision-assertion": (),
        "integration-all": ("lint-typecheck-contracts-security",),
        "test-suites": ("lint-typecheck-contracts-security",),
        "lint-typecheck-contracts-security": ("windows-lock-closures",),
        "windows-lock-closures": ("exact-revision-assertion",),
        "coverage-gate": ("test-suites",),
        "docker-build": ("coverage-gate",),
    }
    for name, dependencies in expected_edges.items():
        job = jobs[name]
        assert _needs(job) == dependencies, name
        assert "if" not in job, name
        assert "continue-on-error" not in job, name
        for step in job["steps"]:
            assert "continue-on-error" not in step, (name, step)
            if "run" in step:
                assert "if" not in step, (name, step)

    integration = jobs["integration-all"]
    assert integration["name"] == "Main Releasability / Integration Full"
    assert integration["runs-on"] == "ubuntu-latest"
    assert integration["timeout-minutes"] == 90
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert not any("download-artifact" in step.get("uses", "") for step in integration["steps"])


def test_full_integration_overlaps_shards_without_bypassing_source_or_coverage() -> None:
    _assert_parallel_integration_admission(_workflow())


@pytest.mark.parametrize(
    ("expected_sha", "reachable", "exit_code"),
    [("reviewed", "0", 0), ("different", "0", 1), ("reviewed", "1", 1)],
)
def test_exact_revision_script_accepts_main_and_refuses_wrong_or_unreachable_sha(
    expected_sha: str, reachable: str, exit_code: int
) -> None:
    git_path = shutil.which("git")
    git_bash = Path(git_path).parent.parent / "bin/bash.exe" if git_path else Path()
    bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
    assert bash, "Exact-revision shell proof requires Bash, as does the hosted job"
    command = _workflow()["jobs"]["exact-revision-assertion"]["steps"][1]["run"]
    # Execute the actual workflow shell with only Git I/O substituted; never fetch or mutate refs.
    git_io = """
    git() {
      case "$1" in
        rev-parse) printf '%s\\n' reviewed ;;
        fetch) return 0 ;;
        merge-base) return "$REACHABLE_EXIT" ;;
        *) return 97 ;;
      esac
    }
    """
    result = subprocess.run(
        [bash, "-e", "-c", git_io + command],
        env={**os.environ, "EXPECTED_SHA": expected_sha, "REACHABLE_EXIT": reachable},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == exit_code, result.stderr
    assert ("Validated exact merged PR SHA" in result.stdout) == (exit_code == 0)


@pytest.mark.parametrize(
    ("job_name", "field", "value"),
    [
        ("integration-all", "needs", ["exact-revision-assertion"]),
        ("integration-all", "needs", ["coverage-gate"]),
        ("lint-typecheck-contracts-security", "needs", []),
        ("windows-lock-closures", "needs", []),
        ("exact-revision-assertion", "continue-on-error", True),
        ("lint-typecheck-contracts-security", "continue-on-error", True),
        ("docker-build", "needs", ["integration-all"]),
        ("coverage-gate", "needs", []),
        ("integration-all", "if", "always()"),
        ("integration-all", "continue-on-error", True),
        ("coverage-gate", "continue-on-error", True),
        ("docker-build", "if", "always()"),
    ],
)
def test_parallel_integration_rejects_admission_and_release_bypasses(
    job_name: str, field: str, value: object
) -> None:
    workflow = _workflow()
    workflow["jobs"][job_name][field] = value
    with pytest.raises(AssertionError):
        _assert_parallel_integration_admission(workflow)


def test_integration_full_retains_test_progress_and_bounded_wait_diagnostics() -> None:
    job = _workflow()["jobs"]["integration-all"]
    assert job["timeout-minutes"] == 90
    run_step = next(
        step for step in job["steps"] if step.get("name") == "Run full integration suite"
    )
    assert run_step["run"] == "make test-integration-all"
    environment = run_step["env"]
    options = suite_pytest_command("integration-all", quiet=True)
    assert "-vv" in options
    assert "faulthandler_timeout=120" in options
    report_path = "output/integration-all/integration-all-results.xml"
    assert f"--junitxml={report_path}" in options
    upload_step = next(
        step for step in job["steps"] if step.get("name") == "Upload integration diagnostics"
    )
    assert upload_step["if"] == "always()"
    artifact_paths = upload_step["with"]["path"].splitlines()
    assert report_path in artifact_paths
    assert environment["LOTUS_TESTS_COMPOSE_LOG_FILE"] in artifact_paths
    assert "output/integration-all/*-progress.jsonl" in artifact_paths
    assert "output/integration-all/*-process.json" in artifact_paths


def _depends_on_exact_revision(
    job_name: str,
    jobs: dict[str, dict[str, object]],
    visiting: frozenset[str] = frozenset(),
) -> bool:
    if job_name == "exact-revision-assertion":
        return True
    if job_name in visiting:
        return False
    return any(
        _depends_on_exact_revision(dependency, jobs, visiting | {job_name})
        for dependency in _needs(jobs[job_name])
    )


def test_main_releasability_is_bound_to_exact_dispatched_main_revision() -> None:
    workflow = _workflow()
    trigger = workflow[True]

    assert set(trigger) == {"workflow_dispatch"}
    inputs = trigger["workflow_dispatch"]["inputs"]
    assert {"expected_sha", "triggering_pr", "source_branch"} <= set(inputs)
    assert workflow["concurrency"]["group"] == (
        "${{ github.workflow }}-${{ inputs.expected_sha || github.sha }}"
    )
    resolved_source_branch = "${{ inputs.source_branch || github.ref_name }}"
    assert workflow["env"]["LOTUS_GIT_BRANCH"] == resolved_source_branch

    jobs = workflow["jobs"]
    assertion = jobs["exact-revision-assertion"]
    command = assertion["steps"][1]["run"]
    assert 'if [ "$actual_sha" != "$EXPECTED_SHA" ]' in command
    assert "git fetch --no-tags origin main:refs/remotes/origin/main" in command
    assert 'git merge-base --is-ancestor "$EXPECTED_SHA" origin/main' in command
    for job_name in jobs:
        assert _depends_on_exact_revision(job_name, jobs), job_name

    docker_build = jobs["docker-build"]
    build_step = next(
        step
        for step in docker_build["steps"]
        if step.get("name") == "Build exact-source runtime image set"
    )
    assert build_step["env"]["LOTUS_RUNTIME_IMAGE_SET_SOURCE_BRANCH"] == resolved_source_branch


def test_institutional_completion_gate_is_manual_opt_in() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "run_institutional_completion:" in workflow
    assert (
        'description: "Run the bounded 100-portfolio institutional completion and sign-off jobs."'
    ) in workflow
    assert "default: false" in workflow
    assert "type: boolean" in workflow
    assert (
        "if: ${{ github.event_name == 'workflow_dispatch' && inputs.run_institutional_completion }}"
    ) in workflow


def test_institutional_completion_is_not_default_merge_or_manual_truth() -> None:
    runbook = Path("docs/operations/Institutional-Signoff-Runbook.md").read_text(encoding="utf-8")

    assert "run_institutional_completion=true" in runbook
    assert "Exact-merge-SHA dispatcher runs and default manual runs intentionally skip" in runbook
    assert "100-portfolio institutional completion" in runbook
