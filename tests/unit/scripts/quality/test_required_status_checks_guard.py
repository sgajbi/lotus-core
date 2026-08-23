from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.required_status_checks_guard import (
    DEFAULT_MANIFEST_PATH,
    RequiredCheck,
    RequiredStatusChecksError,
    WorkflowPolicy,
    blocking_contexts_for_workflow,
    load_manifest,
    validate_live_protection,
    validate_manifest_against_workflows,
)


def test_repository_manifest_matches_expanded_blocking_workflow_contexts() -> None:
    manifest = load_manifest()

    validate_manifest_against_workflows(manifest)

    assert len(manifest.required_checks) == 37
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
    with pytest.raises(RequiredStatusChecksError, match="live branch-protection drift"):
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
