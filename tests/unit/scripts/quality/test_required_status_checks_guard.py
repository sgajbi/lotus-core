from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from scripts.quality.required_status_checks_guard import (
    DEFAULT_MANIFEST_PATH,
    RequiredCheck,
    RequiredStatusChecksError,
    WorkflowPolicy,
    blocking_contexts_for_workflow,
    desired_protection_payload,
    load_live_protection,
    load_manifest,
    validate_live_protection,
    validate_manifest_against_workflows,
)


def test_repository_manifest_matches_expanded_blocking_workflow_contexts() -> None:
    manifest = load_manifest()

    validate_manifest_against_workflows(manifest)

    assert (
        RequiredCheck(
            context="PR Merge Gate / Tests (transaction-processing-contract)",
            app_id=15368,
        )
        in manifest.required_checks
    )
    assert (
        RequiredCheck(
            context="Quality Baseline / Import Boundary Gate",
            app_id=15368,
        )
        in manifest.required_checks
    )
    assert all(
        check.context != "Quality Baseline / Report Only" for check in manifest.required_checks
    )


def test_matrix_contexts_expand_from_each_include_row() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {
                    "matrix": {
                        "include": [
                            {"suite": "unit", "target": "test-unit"},
                            {"suite": "transaction-processing-contract", "target": "ignored"},
                        ]
                    }
                },
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "PR Merge Gate / Tests (unit)",
        "PR Merge Gate / Tests (transaction-processing-contract)",
    )


def test_matrix_context_expansion_treats_values_as_literal_text() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": r"windows\proof"}]}},
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        r"PR Merge Gate / Tests (windows\proof)",
    )


def test_gate_policy_rejects_an_undeclared_non_gate_job() -> None:
    workflow = {"jobs": {"ambiguous": {"name": "Quality Baseline / Quietly Optional"}}}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="neither a blocking Gate nor declared"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_gate_policy_excludes_only_an_explicit_observed_advisory_context() -> None:
    workflow = {
        "jobs": {
            "gate": {"name": "Quality Baseline / Security Gate"},
            "report": {"name": "Quality Baseline / Report Only"},
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset({"Quality Baseline / Report Only"}),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_manifest_validation_rejects_a_new_workflow_gate_before_protection_can_drift(
    tmp_path: Path,
) -> None:
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_path = tmp_path / "quality.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": "quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": [],
        }
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Existing Gate", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    workflow_path.write_text(
        "jobs:\n"
        "  existing:\n"
        "    name: Quality Baseline / Existing Gate\n"
        "  new_control:\n"
        "    name: Quality Baseline / New Control Gate\n",
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_path)

    with pytest.raises(RequiredStatusChecksError, match="New Control Gate"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_live_protection_requires_exact_context_app_binding_and_strict_mode() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]
    protection = {"required_status_checks": {"strict": True, "checks": live_checks}}

    validate_live_protection(manifest, protection)

    protection["required_status_checks"]["checks"][0]["app_id"] = -1
    with pytest.raises(RequiredStatusChecksError, match="invalid context or app_id"):
        validate_live_protection(manifest, protection)

    protection["required_status_checks"]["checks"][0]["app_id"] = 15368
    protection["required_status_checks"]["strict"] = False
    with pytest.raises(RequiredStatusChecksError, match="strict mode differs"):
        validate_live_protection(manifest, protection)


def test_live_protection_rejects_missing_and_stale_contexts() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks[1:]
    ]
    live_checks.append({"context": "Retired / Stale Gate", "app_id": 15368})

    with pytest.raises(RequiredStatusChecksError, match="missing=.*stale="):
        validate_live_protection(
            manifest,
            {"required_status_checks": {"strict": True, "checks": live_checks}},
        )


def test_live_protection_rejects_boolean_app_identity() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]
    live_checks[0]["app_id"] = True

    with pytest.raises(RequiredStatusChecksError, match="context=.*Coverage Gate"):
        validate_live_protection(
            manifest,
            {"required_status_checks": {"strict": True, "checks": live_checks}},
        )


def test_desired_payload_is_app_bound_and_ready_for_atomic_update() -> None:
    manifest = load_manifest()

    payload = desired_protection_payload(manifest)

    assert payload == {
        "strict": True,
        "checks": [
            {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
        ],
    }


def test_live_reader_fails_before_subprocess_when_secret_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(RequiredStatusChecksError, match="READ_TOKEN is not provisioned"):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")

    run.assert_not_called()


def test_live_reader_retains_bounded_http_failure_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            side_effect=subprocess.CalledProcessError(
                returncode=1,
                cmd=["gh", "api"],
                stderr="gh: Resource not accessible by integration (HTTP 403)\nsecond line",
            )
        ),
    )

    with pytest.raises(RequiredStatusChecksError, match="HTTP 403") as exc_info:
        load_live_protection(repository="sgajbi/lotus-core", branch="main")

    assert "sentinel-secret" not in str(exc_info.value)
    assert "second line" not in str(exc_info.value)


def test_live_reader_reports_timeout_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=30)),
    )

    with pytest.raises(RequiredStatusChecksError, match="read timed out"):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")


def test_required_local_gates_are_reachable_from_lint_and_workflow_governance() -> None:
    makefile_lines = Path("Makefile").read_text(encoding="utf-8").splitlines()
    dependencies = {
        target: values.split()
        for line in makefile_lines
        if ":" in line and not line.startswith(("\t", "#", "."))
        for target, values in (line.split(":", maxsplit=1),)
    }
    makefile_text = "\n".join(makefile_lines)

    assert "quality-import-boundary-gate" in dependencies["lint"]
    assert "required-status-checks-guard" in dependencies["lint"]
    assert "required-status-checks-guard:" in makefile_text
    assert "required-status-checks-live-guard:" in makefile_text
    assert "test_required_status_checks_guard.py" in makefile_text


def test_main_releasability_verifies_live_protection_read_only() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/main-releasability.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["lint-typecheck-contracts-security"]["steps"]
    parity_step = next(
        step for step in steps if step.get("name") == "Verify live required status checks"
    )

    assert parity_step == {
        "name": "Verify live required status checks",
        "env": {"GH_TOKEN": "${{ secrets.LOTUS_BRANCH_PROTECTION_READ_TOKEN }}"},
        "run": "make required-status-checks-live-guard",
    }
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
