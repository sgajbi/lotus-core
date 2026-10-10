"""Positive and rejecting controls for the audited local acquisition action."""

import copy

import pytest
import yaml

from scripts.quality.required_status_checks import image_acquisition_action as policy
from scripts.quality.required_status_checks.action_policy import validate_step_action
from scripts.quality.required_status_checks.model import RequiredStatusChecksError


def _payload():
    return yaml.safe_load(policy.ACTION_PATH.read_text(encoding="utf-8"))


def _step(scope="compose"):
    inputs = {"scope": scope}
    if scope == "compose":
        inputs.update(
            {
                "dockerhub-username": "${{ secrets.DOCKERHUB_USERNAME }}",
                "dockerhub-read-token": "${{ secrets.DOCKERHUB_READ_TOKEN }}",
            }
        )
    return {"uses": policy.ACTION, "with": inputs}


@pytest.mark.parametrize("scope", ["python", "compose", "release"])
def test_existing_guard_accepts_audited_action(scope):
    validate_step_action(
        _step(scope),
        enforcement=False,
        context_text="Core",
        step_name="acquisition",
        runner="ubuntu-latest",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "mutable_ref",
        "new_step",
        "failure_suppressed",
        "native_check_skipped",
        "credentials_printed",
        "failure_evidence_skipped",
    ],
)
def test_composite_mutation_is_rejected(mutation):
    payload = copy.deepcopy(_payload())
    steps = payload["runs"]["steps"]
    if mutation == "mutable_ref":
        steps[0]["with"]["ref"] = "main"
    elif mutation == "new_step":
        steps.append({"run": "echo success", "shell": "bash"})
    elif mutation == "failure_suppressed":
        steps[1]["continue-on-error"] = True
    elif mutation == "native_check_skipped":
        steps[1]["if"] = "false"
    elif mutation == "credentials_printed":
        steps[1]["run"] += "; printenv"
    else:
        steps[2]["if"] = "success()"
    with pytest.raises(RequiredStatusChecksError, match="execution drifted"):
        policy.validate_action_payload(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "all"),
        ("evidence-id", "${{ secrets.GITHUB_TOKEN }}"),
        ("dockerhub-read-token", "${{ github.token }}"),
        ("dockerhub-username", "unrelated-account"),
    ],
)
def test_unapproved_input_cannot_reach_action(field, value):
    step = _step()
    step["with"][field] = value
    with pytest.raises(RequiredStatusChecksError, match="not audited"):
        policy.validate_action_inputs(step, step["with"])


def test_only_named_matrix_condition_is_admitted():
    step = _step()
    step["if"] = policy.COMPOSE_MATRIX_CONDITION
    step["with"]["evidence-id"] = "${{ strategy.job-index }}"
    policy.validate_action_inputs(step, step["with"])
    step["if"] = "false"
    with pytest.raises(RequiredStatusChecksError, match="condition is not audited"):
        policy.validate_action_inputs(step, step["with"])


@pytest.mark.parametrize("content", [None, "[", "[]"])
def test_missing_or_invalid_composite_fails_closed(tmp_path, monkeypatch, content):
    path = tmp_path / "action.yml"
    monkeypatch.setattr(policy, "ACTION_PATH", path)
    if content is not None:
        path.write_text(content, encoding="utf-8")
    step = _step()
    with pytest.raises(RequiredStatusChecksError):
        policy.validate_action_inputs(step, step["with"])
