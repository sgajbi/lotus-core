from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/main-releasability.yml")


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _needs(job: dict[str, object]) -> tuple[str, ...]:
    value = job.get("needs", ())
    if isinstance(value, str):
        return (value,)
    return tuple(value)  # type: ignore[arg-type]


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
        'description: "Run the approval-grade 1000-portfolio institutional completion '
        'and sign-off jobs."'
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
    assert "1000-portfolio institutional completion" in runbook
