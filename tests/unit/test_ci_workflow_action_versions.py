from pathlib import Path

import yaml

GOVERNED_RUNTIME_WORKFLOWS = (
    Path(".github/workflows/pr-merge-gate.yml"),
    Path(".github/workflows/main-releasability.yml"),
)

ALL_WORKFLOWS = tuple(Path(".github/workflows").glob("*.yml"))

APPROVED_NON_BLOCKING_JOBS = {
    (Path(".github/workflows/pr-merge-gate.yml"), "lotus-core-validation-report"),
}

APPROVED_REPORT_ONLY_STEPS = {
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Ruff baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Test collection baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Typecheck baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Complexity baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Maintainability baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Dead-code baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Dependency baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Security baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Dependency audit baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Import boundary baseline",
    ),
    (
        Path(".github/workflows/quality-baseline.yml"),
        "report-only",
        "Docstring baseline",
    ),
}

NODE20_DEPRECATED_ACTION_PINS = (
    "actions/cache@v4",
    "actions/upload-artifact@v4",
    "actions/download-artifact@v4",
    "actions/upload-artifact@v5",
    "actions/download-artifact@v5",
    "docker/setup-buildx-action@v3",
)

EXPECTED_RUNTIME_ACTION_PINS = (
    "actions/cache@v5",
    "actions/upload-artifact@v7",
    "docker/setup-buildx-action@v4",
)


def test_runtime_workflows_do_not_use_node20_deprecated_action_pins() -> None:
    deprecated_pins: list[str] = []
    for workflow_path in GOVERNED_RUNTIME_WORKFLOWS:
        workflow_text = workflow_path.read_text(encoding="utf-8")
        for action_pin in NODE20_DEPRECATED_ACTION_PINS:
            if action_pin in workflow_text:
                deprecated_pins.append(f"{workflow_path}: {action_pin}")

    assert deprecated_pins == []


def test_runtime_workflows_use_current_action_pins_for_cache_artifacts_and_buildx() -> None:
    workflow_text = "\n".join(
        workflow_path.read_text(encoding="utf-8") for workflow_path in GOVERNED_RUNTIME_WORKFLOWS
    )

    for action_pin in EXPECTED_RUNTIME_ACTION_PINS:
        assert action_pin in workflow_text

    assert "actions/download-artifact@v8" in Path(
        ".github/workflows/main-releasability.yml"
    ).read_text(encoding="utf-8")


def test_workflows_opt_into_node24_action_runtime() -> None:
    missing_opt_in = [
        str(workflow_path)
        for workflow_path in ALL_WORKFLOWS
        if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"'
        not in workflow_path.read_text(encoding="utf-8")
    ]

    assert missing_opt_in == []


def test_runtime_latency_gates_use_bounded_demo_seed_history() -> None:
    for workflow_path in GOVERNED_RUNTIME_WORKFLOWS:
        workflow_text = workflow_path.read_text(encoding="utf-8")
        assert 'DEMO_DATA_PACK_HISTORY_DAYS: "365"' in workflow_text
        assert 'DEMO_DATA_PACK_PORTFOLIO_IDS: "DEMO_DPM_EUR_001"' in workflow_text


def test_pr_auto_merge_does_not_probe_branch_protection_with_github_token() -> None:
    workflow_text = Path(".github/workflows/pr-auto-merge.yml").read_text(encoding="utf-8")

    assert "/branches/main/protection" not in workflow_text
    assert "administration:" not in workflow_text


def test_pr_auto_merge_does_not_emit_skipped_checks_for_label_removal() -> None:
    workflow_text = Path(".github/workflows/pr-auto-merge.yml").read_text(encoding="utf-8")

    assert "labeled" in workflow_text
    assert "unlabeled" not in workflow_text
    assert "HAS_AUTOMERGE_LABEL:" in workflow_text
    assert "Skipping auto-merge queue because the automerge label is absent." in workflow_text


def test_all_workflow_jobs_have_bounded_timeouts() -> None:
    missing_or_invalid_timeouts: list[str] = []

    for workflow_path in ALL_WORKFLOWS:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
        for job_id, job in (workflow.get("jobs") or {}).items():
            timeout_minutes = job.get("timeout-minutes")
            if not isinstance(timeout_minutes, int) or timeout_minutes <= 0:
                missing_or_invalid_timeouts.append(f"{workflow_path}:{job_id}")

    assert missing_or_invalid_timeouts == []


def test_continue_on_error_is_limited_to_documented_report_only_scope() -> None:
    unexpected_non_blocking_jobs: list[str] = []
    unexpected_non_blocking_steps: list[str] = []

    for workflow_path in ALL_WORKFLOWS:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
        for job_id, job in (workflow.get("jobs") or {}).items():
            if (
                job.get("continue-on-error")
                and (
                    workflow_path,
                    job_id,
                )
                not in APPROVED_NON_BLOCKING_JOBS
            ):
                unexpected_non_blocking_jobs.append(f"{workflow_path}:{job_id}")

            for step in job.get("steps") or ():
                step_name = step.get("name", "<unnamed step>")
                if (
                    step.get("continue-on-error")
                    and (
                        workflow_path,
                        job_id,
                        step_name,
                    )
                    not in APPROVED_REPORT_ONLY_STEPS
                ):
                    unexpected_non_blocking_steps.append(f"{workflow_path}:{job_id}:{step_name}")

    assert unexpected_non_blocking_jobs == []
    assert unexpected_non_blocking_steps == []


def test_quality_baseline_runs_workflow_governance_gate() -> None:
    workflow_text = Path(".github/workflows/quality-baseline.yml").read_text(encoding="utf-8")
    makefile_text = Path("Makefile").read_text(encoding="utf-8")

    assert "quality-workflow-governance-gate:" in makefile_text
    assert "Quality Baseline / Workflow Governance Gate" in workflow_text
    assert "make quality-workflow-governance-gate" in workflow_text


def test_quality_baseline_runs_manifest_integration_lite_collection_gate() -> None:
    workflow_text = Path(".github/workflows/quality-baseline.yml").read_text(encoding="utf-8")
    makefile_text = Path("Makefile").read_text(encoding="utf-8")

    assert "quality-integration-lite-collection-gate:" in makefile_text
    assert "Quality Baseline / Integration Lite Collection Gate" in workflow_text
    assert "make quality-integration-lite-collection-gate" in workflow_text
