from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.quality import required_status_checks_guard as cli
from scripts.quality.required_status_checks import (
    DEFAULT_MANIFEST_PATH,
    RequiredStatusChecksError,
    WorkflowPolicy,
    blocking_contexts_for_workflow,
    load_live_protection,
    load_manifest,
    validate_live_protection,
)


def _write_manifest(tmp_path: Path, payload: object) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("non_object", "must be a JSON object"),
        ("unknown_field", "unexpected shape"),
        ("schema_version", "unsupported.*schema_version"),
        ("strict_type", "strict must be a boolean"),
        ("empty_policies", "workflow_policies must be a non-empty list"),
        ("policy_shape", "workflow_policies.*unexpected shape"),
        ("unsupported_policy", "unsupported workflow policy"),
        ("advisory_type", "advisory_contexts must be a list"),
        ("duplicate_advisory", "advisory contexts must be unique"),
        ("empty_checks", "required_checks must be a non-empty list"),
        ("check_shape", "required_checks.*unexpected shape"),
        ("invalid_app_id", "app_id must be a positive integer"),
        ("unsorted_checks", "required_checks must be sorted"),
        ("duplicate_checks", "required_checks must be unique"),
    ],
)
def test_manifest_shape_mutations_fail_closed(tmp_path: Path, mutation: str, match: str) -> None:
    payload = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    if mutation == "non_object":
        payload = []
    elif mutation == "unknown_field":
        payload["unexpected"] = True
    elif mutation == "schema_version":
        payload["schema_version"] = 2
    elif mutation == "strict_type":
        payload["strict"] = "true"
    elif mutation == "empty_policies":
        payload["workflow_policies"] = []
    elif mutation == "policy_shape":
        payload["workflow_policies"][0].pop("policy")
    elif mutation == "unsupported_policy":
        payload["workflow_policies"][0]["policy"] = "best_effort"
    elif mutation == "advisory_type":
        payload["workflow_policies"][0]["advisory_contexts"] = "Report Only"
    elif mutation == "duplicate_advisory":
        payload["workflow_policies"][0]["advisory_contexts"] = ["A", "A"]
    elif mutation == "empty_checks":
        payload["required_checks"] = []
    elif mutation == "check_shape":
        payload["required_checks"][0]["unexpected"] = True
    elif mutation == "invalid_app_id":
        payload["required_checks"][0]["app_id"] = False
    elif mutation == "unsorted_checks":
        payload["required_checks"] = list(reversed(payload["required_checks"]))
    elif mutation == "duplicate_checks":
        payload["required_checks"].insert(1, payload["required_checks"][0].copy())

    with pytest.raises(RequiredStatusChecksError, match=match):
        load_manifest(_write_manifest(tmp_path, payload))


def test_manifest_reader_reports_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(RequiredStatusChecksError, match="unable to load"):
        load_manifest(tmp_path / "missing.json")
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    with pytest.raises(RequiredStatusChecksError, match="unable to load"):
        load_manifest(malformed_path)


@pytest.mark.parametrize(
    ("job", "match"),
    [
        ({"name": "PR Merge Gate / Gate", "steps": "invalid"}, "steps must be a list"),
        ({"name": "PR Merge Gate / Gate", "steps": ["invalid"]}, "step must be an object"),
        (
            {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"target": "test-unit"}]}},
                "steps": [{"run": "make test"}],
            },
            "include row lacks suite",
        ),
        (
            {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": "unit"}, {"suite": "unit"}]}},
                "steps": [{"run": "make test"}],
            },
            "matrix values must be unique",
        ),
    ],
)
def test_blocking_workflow_shape_mutations_fail_closed(job: dict[str, object], match: str) -> None:
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )
    with pytest.raises(RequiredStatusChecksError, match=match):
        blocking_contexts_for_workflow({"jobs": {"gate": job}}, policy=policy)


def test_live_protection_rejects_malformed_shapes() -> None:
    manifest = load_manifest()
    with pytest.raises(RequiredStatusChecksError, match="no required_status_checks"):
        validate_live_protection(manifest, {})
    with pytest.raises(RequiredStatusChecksError, match="app-bound checks"):
        validate_live_protection(manifest, {"required_status_checks": {"strict": True}})
    with pytest.raises(RequiredStatusChecksError, match="must be an object"):
        validate_live_protection(
            manifest,
            {"required_status_checks": {"strict": True, "checks": ["invalid"]}},
        )


@pytest.mark.parametrize(
    ("failure", "match"),
    [
        (OSError("missing gh"), "unable to start"),
        (subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=30), "timed out"),
    ],
)
def test_live_reader_reports_process_failures(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, match: str
) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(RequiredStatusChecksError, match=match):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")


def test_live_reader_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(args=["gh", "api"], returncode=0, stdout="{")
        ),
    )
    with pytest.raises(RequiredStatusChecksError, match="malformed JSON"):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")


def test_cli_prints_atomic_payload_and_fails_for_missing_manifest(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert cli.main(["--print-desired-protection"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["strict"] is True
    assert payload["contexts"] == []
    assert len(payload["checks"]) == 37

    assert cli.main(["--manifest", str(tmp_path / "missing.json")]) == 1
    assert "unable to load required-check manifest" in capsys.readouterr().out
