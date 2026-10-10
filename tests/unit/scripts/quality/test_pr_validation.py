"""Lane selection, authority refusals and actual unit/warning/coverage producer behavior."""

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from coverage import Coverage

from scripts.quality import coverage_gate, test_manifest
from scripts.quality.pr_validation import __main__ as dispatch
from scripts.quality.pr_validation import contract, feature_authority, policy


def test_fixed_native_targets_cannot_be_replaced_by_receipt_or_arbitrary_command():
    for target in policy.TARGETS:
        assert policy.selected_commands(target, "full") == (("make", target),)
        assert policy.selected_commands(target, "unknown") == (("make", target),)
        selected = policy.selected_commands(target, "docs-only")
        assert selected[0] == ("make", "quality-wiki-docs-gate")
        assert selected[1] == ("make", "docs-evidence-pack")
        if target in policy.TEST_TARGETS:
            assert "--collect-only" in selected[2]
            assert policy.TEST_TARGETS[target] in selected[2]
    with pytest.raises(ValueError, match="unregistered"):
        policy.selected_commands("echo success", "docs-only")


@pytest.mark.parametrize("mode", ["full", "docs-only"])
@pytest.mark.parametrize("child_exit", [0, 1, 7])
def test_dispatch_propagates_native_failure_and_records_decision(
    tmp_path, monkeypatch, mode, child_exit
):
    monkeypatch.setattr(dispatch, "ROOT", tmp_path)
    (tmp_path / "output/pr-validation").mkdir(parents=True)
    evidence_directory = tmp_path / "output/documentation-evidence"
    evidence_directory.mkdir()
    (evidence_directory / "documentation-evidence-pack.json").write_text(
        '{"producer": "test-composition-double"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        dispatch, "current_plan", lambda: {"mode": mode, "source_head_sha": "verified"}
    )
    monkeypatch.setattr(dispatch, "emit", lambda plan: None)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=child_exit)

    monkeypatch.setattr(dispatch.subprocess, "run", run)
    assert dispatch.run_target("coverage-shard-unit") == child_exit
    assert calls[0][0] == "make"
    assert len(calls) == (3 if mode == "docs-only" and child_exit == 0 else 1)
    receipt = json.loads((tmp_path / "output/pr-validation/coverage-shard-unit.json").read_text())
    assert receipt["native_exit"] == child_exit
    assert receipt["source_head_sha"] == "verified"
    assert receipt["command_results"][-1]["native_exit"] == child_exit
    if mode == "docs-only" and child_exit == 0:
        assert receipt["documentation_evidence_pack"]["producer"] == "test-composition-double"


@pytest.fixture
def hosted_feature(monkeypatch):
    head = "a" * 40
    monkeypatch.setattr(feature_authority, "git", lambda *args: head)
    for key, value in {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_WORKFLOW": "Remote Feature Lane",
        "GITHUB_REPOSITORY": feature_authority.REPOSITORY,
        "GITHUB_SHA": head,
    }.items():
        monkeypatch.setenv(key, value)
    pull = {
        "state": "open",
        "number": 123,
        "head": {"sha": head},
        "base": {"ref": "main", "repo": {"full_name": feature_authority.REPOSITORY}},
    }
    run = {
        "id": 456,
        "head_sha": head,
        "event": "pull_request",
        "status": "queued",
        "path": ".github/workflows/pr-merge-gate.yml",
        "pull_requests": [{"number": 123}],
    }
    monkeypatch.setattr(
        feature_authority,
        "api",
        lambda path: [pull] if "/pulls?" in path else {"workflow_runs": [run]},
    )
    return pull, run


def test_feature_defers_only_to_positive_exact_head_required_pr_authority(hosted_feature):
    plan = feature_authority.feature_plan()
    assert plan["run_feature"] is False
    assert plan["pr_number"] == 123
    assert plan["pr_run_id"] == 456


@pytest.mark.parametrize(
    "change",
    [
        "closed",
        "wrong-head",
        "wrong-base",
        "wrong-run-head",
        "wrong-workflow",
        "unassociated",
        "unknown-status",
    ],
)
def test_feature_preserves_full_unit_fallback_for_ambiguous_authority(hosted_feature, change):
    pull, run = hosted_feature
    if change == "closed":
        pull["state"] = "closed"
    elif change == "wrong-head":
        pull["head"]["sha"] = "b" * 40
    elif change == "wrong-base":
        pull["base"]["ref"] = "other"
    elif change == "wrong-run-head":
        run["head_sha"] = "b" * 40
    elif change == "wrong-workflow":
        run["path"] = ".github/workflows/other.yml"
    elif change == "unassociated":
        run["pull_requests"] = []
    else:
        run["status"] = "unknown"
    assert feature_authority.feature_plan()["run_feature"] is True


@pytest.mark.parametrize("failure", [OSError(), ValueError(), subprocess.TimeoutExpired("gh", 30)])
def test_feature_api_failure_retains_full_unit_owner(hosted_feature, monkeypatch, failure):
    def fail(path):
        raise failure

    monkeypatch.setattr(feature_authority, "api", fail)
    assert feature_authority.feature_plan()["run_feature"] is True


def test_cancelled_pr_run_and_api_absence_keep_feature_full_unit(hosted_feature, monkeypatch):
    _, run = hosted_feature
    run.update(status="completed", conclusion="cancelled")
    assert feature_authority.feature_plan()["run_feature"] is True
    monkeypatch.setattr(feature_authority, "api", lambda path: [])
    assert feature_authority.feature_plan()["run_feature"] is True


@pytest.fixture
def workflows():
    return [
        yaml.safe_load((contract.ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
        for name in ("pr-merge-gate.yml", "main-releasability.yml", "feature-lane.yml")
    ]


def test_committed_workflow_contract_has_all_required_owners(workflows):
    contract.validate_workflows(*workflows)


@pytest.mark.parametrize(
    "damage",
    [None, "skip-job", "tooling-only", "conditional-install", "late-install", "missing-install"],
)
def test_guard_entrypoint_preserves_valid_and_bad_native_exit(
    workflows, tmp_path, monkeypatch, damage
):
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True)
    pr, main, feature = copy.deepcopy(workflows)
    if damage == "skip-job":
        pr["jobs"]["coverage-gate"]["if"] = "false"
    elif damage:
        steps = pr["jobs"]["docker-build"]["steps"]
        installer = next(step for step in steps if step.get("run") == "make install-ci")
        if damage == "tooling-only":
            installer["run"] = "make install-ci-tooling"
        elif damage == "conditional-install":
            installer["if"] = "false"
        else:
            steps.remove(installer)
            if damage == "late-install":
                steps.append(installer)
    for name, workflow in zip(
        ("pr-merge-gate.yml", "main-releasability.yml", "feature-lane.yml"),
        (pr, main, feature),
        strict=True,
    ):
        (directory / name).write_text(yaml.safe_dump(workflow), encoding="utf-8")
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    assert contract.main() == int(damage is not None)


@pytest.mark.parametrize(
    "damage",
    [
        "missing-matrix",
        "skipped-job",
        "missing-classifier",
        "skipped-enforcement",
        "unwrapped-target",
        "missing-evidence",
        "duplicate-unit",
        "main-docs-dispatch",
        "missing-main-unit",
        "missing-feature-fallback",
        "missing-feature-route",
    ],
)
def test_workflow_contract_refuses_representative_proof_losses(workflows, damage):
    pr, main, feature = copy.deepcopy(workflows)
    job = pr["jobs"]["coverage-gate"]
    if damage == "missing-matrix":
        pr["jobs"]["test-suites"]["strategy"]["matrix"]["include"].pop()
    elif damage == "skipped-job":
        job["if"] = "false"
    elif damage == "missing-classifier":
        job["steps"] = [step for step in job["steps"] if step.get("id") != "classify"]
    elif damage == "skipped-enforcement":
        next(step for step in job["steps"] if step.get("id") == "enforce")["if"] = "false"
    elif damage == "unwrapped-target":
        next(step for step in job["steps"] if step.get("id") == "enforce")["run"] = (
            "make coverage-aggregate"
        )
    elif damage == "missing-evidence":
        job["steps"] = [
            step
            for step in job["steps"]
            if step.get("name") != "Upload exact-source validation selection"
        ]
    elif damage == "duplicate-unit":
        main["jobs"]["lint-typecheck-contracts-security"]["steps"].append(
            {"run": "make warning-gate"}
        )
    elif damage == "main-docs-dispatch":
        main["jobs"]["coverage-gate"]["steps"].append({"run": "make pr-coverage-aggregate"})
    elif damage == "missing-main-unit":
        main["jobs"]["test-suites"]["strategy"]["matrix"]["include"][0]["target"] = "other"
    elif damage == "missing-feature-fallback":
        feature["jobs"]["lint-typecheck-contracts-security"]["steps"] = []
    else:
        feature["jobs"]["test-suites"].pop("if")
    with pytest.raises(ValueError):
        contract.validate_workflows(pr, main, feature)


@pytest.mark.parametrize(
    ("body", "expected_exit", "warning_count"),
    [
        ("assert value() == 1", 0, 0),
        ("assert value() == 2", 1, 0),
        ("warnings.warn('actual producer warning', UserWarning)\n    assert value() == 1", 1, 1),
    ],
)
def test_actual_unit_warning_coverage_owner_propagates_real_child_outcomes(
    tmp_path, monkeypatch, capfd, body, expected_exit, warning_count
):
    """A miniature population executes unchanged native selection/owner code, never a mock."""
    native_manifest = Path(test_manifest.__file__).read_bytes()
    copied = tmp_path / "scripts/quality/test_manifest.py"
    copied.parent.mkdir(parents=True)
    copied.write_bytes(native_manifest)
    assert copied.read_bytes() == native_manifest
    (tmp_path / "tests/unit").mkdir(parents=True)
    (tmp_path / "fixture_source.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests/unit/test_producer.py").write_text(
        "import warnings\nfrom fixture_source import value\n\ndef test_value():\n    "
        + body
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    coverage_file = tmp_path / ".coverage.owner"
    result = coverage_gate._run_coverage_suite(
        "unit", coverage_sources=("fixture_source",), coverage_file=str(coverage_file)
    )
    assert result == expected_exit
    assert coverage_file.is_file()
    measured = Coverage(data_file=str(coverage_file))
    measured.load()
    assert measured.get_data().lines(str(tmp_path / "fixture_source.py")) == [1, 2]
    output = capfd.readouterr().out
    assert f"Warning budget: suite=unit, warnings={warning_count}, max=0" in output
    assert ("1 failed" if body.startswith("assert value() == 2") else "1 passed") in output
