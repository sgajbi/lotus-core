"""PR selection preserves static transitive Make authority and audited download conditions."""

import json
from pathlib import Path

import pytest

from scripts.quality.required_status_checks import (
    DEFAULT_MANIFEST_PATH,
    RequiredStatusChecksError,
    load_manifest,
)
from scripts.quality.required_status_checks.job_policy import (
    _validate_classified_downloads,
    _validate_step_condition,
)
from scripts.quality.required_status_checks.make_authority import (
    MakeTargetAuthority,
    _pr_dispatch_dependencies,
    validate_make_targets_have_executable_authority,
)


def test_native_pr_dispatch_keeps_full_target_recipe_in_authority_closure():
    command = "$(REPOSITORY_PYTHON) -m scripts.quality.pr_validation coverage-shard-unit"
    native = "$(REPOSITORY_PYTHON) control.py"
    authority = {
        "pr-coverage-shard-unit": MakeTargetAuthority((), (command,), True),
        "coverage-shard-unit": MakeTargetAuthority((), (native,), True),
    }
    commands = {
        "pr-coverage-shard-unit": frozenset({command}),
        "coverage-shard-unit": frozenset({native}),
    }
    validate_make_targets_have_executable_authority(
        frozenset({"pr-coverage-shard-unit"}),
        authority=authority,
        path=Path("Makefile"),
        governed_repository_commands=commands,
    )
    authority["coverage-shard-unit"] = MakeTargetAuthority((), ("echo success",), True)
    with pytest.raises(RequiredStatusChecksError):
        validate_make_targets_have_executable_authority(
            frozenset({"pr-coverage-shard-unit"}),
            authority=authority,
            path=Path("Makefile"),
            governed_repository_commands=commands,
        )


@pytest.mark.parametrize("damage", ["missing", "weakened"])
def test_manifest_selection_policy_cannot_drop_conservative_authority(tmp_path, damage):
    original = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(load_manifest().required_checks) == 39
    if damage == "missing":
        original.pop("pr_validation_policy")
    else:
        original["pr_validation_policy"]["feature_authority"] = "skip-unit"
    candidate = tmp_path / "required-status-checks.json"
    candidate.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(RequiredStatusChecksError):
        load_manifest(candidate)


@pytest.mark.parametrize(
    ("target", "delegate"),
    [
        ("pr-other", "coverage-shard-unit"),
        ("pr-unknown", "unknown"),
    ],
)
def test_mismatched_and_unknown_dispatch_dependencies_refuse(target, delegate):
    with pytest.raises(RequiredStatusChecksError):
        _pr_dispatch_dependencies(
            (f"$(REPOSITORY_PYTHON) -m scripts.quality.pr_validation {delegate}",), target=target
        )
    assert _pr_dispatch_dependencies(("$(REPOSITORY_PYTHON) control.py",), target=target) == ()


def test_download_omission_requires_exact_condition_and_preceding_native_classifier():
    classifier = {"id": "classify", "run": "make change-classification"}
    download = {
        "uses": "actions/download-artifact@v8",
        "if": "steps.classify.outputs.mode != 'docs-only'",
    }
    _validate_step_condition(download, context_text="test", step_name="download")
    _validate_classified_downloads([classifier, download], context="test")
    _validate_classified_downloads([{"uses": "actions/download-artifact@v8"}], context="test")
    for steps in (
        [download],
        [download, classifier],
        [classifier, classifier, download],
        [{"id": "classify", "run": "echo docs-only"}, download],
        [{**classifier, "if": "false"}, download],
    ):
        with pytest.raises(RequiredStatusChecksError):
            _validate_classified_downloads(steps, context="test")
    for condition in ("false", "true", "always()", "steps.classify.outputs.mode == 'full'"):
        with pytest.raises(RequiredStatusChecksError):
            _validate_step_condition(
                {**download, "if": condition}, context_text="test", step_name="download"
            )
