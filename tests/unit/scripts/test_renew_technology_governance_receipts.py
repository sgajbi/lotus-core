from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.development import renew_technology_governance_receipts as renewal
from scripts.quality import technology_governance_pilot_guard as guard

RUN_ID = 123456


def _source_commit() -> str:
    return guard._git_value(guard.REPO_ROOT, "rev-parse", "origin/main")


def _run_payload(*, branch: str | None = None) -> dict[str, object]:
    source_commit = _source_commit()
    return {
        "head_sha": source_commit,
        "workflow_id": guard.RECEIPT_WORKFLOW_ID,
        "path": guard.RECEIPT_WORKFLOW_PATH,
        "event": guard.RENEWABLE_RECEIPT_EVENT,
        "head_branch": branch or f"{guard.RENEWABLE_RECEIPT_BRANCH_PREFIX}{source_commit}",
        "status": "completed",
        "conclusion": "success",
    }


def _jobs_payload(*, conclusion: str = "success") -> dict[str, object]:
    return {
        "jobs": [
            {
                "name": guard.EXACT_REVISION_ASSERTION_JOB,
                "status": "completed",
                "conclusion": conclusion,
            }
        ]
    }


def _artifacts_payload(manifest: dict[str, object]) -> dict[str, object]:
    names = {
        renewal._renewed_artifact_name(str(receipt["artifact"]), RUN_ID)
        for _, receipt in guard._github_run_refs(manifest)
    }
    return {
        "artifacts": [
            {
                "name": name,
                "digest": "sha256:" + f"{index:064x}",
                "expired": False,
                "expires_at": "2099-01-01T00:00:00Z",
            }
            for index, name in enumerate(sorted(names), start=1)
        ]
    }


def _install_github_payloads(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, object],
    *,
    run: dict[str, object] | None = None,
    jobs: dict[str, object] | None = None,
    artifacts: dict[str, object] | None = None,
) -> None:
    def github_payload(endpoint: str) -> dict[str, object]:
        if "/artifacts?" in endpoint:
            return artifacts if artifacts is not None else _artifacts_payload(manifest)
        if "/jobs?" in endpoint:
            return jobs if jobs is not None else _jobs_payload()
        return run if run is not None else _run_payload()

    monkeypatch.setattr(guard, "_github_api_payload", github_payload)


def test_renewal_updates_only_receipts_and_preserves_assessment_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = guard.load_manifest()
    original = copy.deepcopy(manifest)
    _install_github_payloads(monkeypatch, manifest)

    renewed = renewal.renew_manifest(manifest, run_id=RUN_ID)

    assert renewed["inspected_core_commit"] == original["inspected_core_commit"]
    assert renewed["assessment_date"] == original["assessment_date"]
    assert renewed["claim_boundary"] == original["claim_boundary"]
    assert renewed["technology_state_assessment"] == original["technology_state_assessment"]
    source_commit = _source_commit()
    receipts = [receipt for _, receipt in guard._github_run_refs(renewed)]
    assert receipts
    assert {receipt["source_commit"] for receipt in receipts} == {source_commit}
    assert {receipt["event"] for receipt in receipts} == {guard.RENEWABLE_RECEIPT_EVENT}
    assert {receipt["head_branch"] for receipt in receipts} == {
        f"{guard.RENEWABLE_RECEIPT_BRANCH_PREFIX}{source_commit}"
    }
    assert any(
        receipt["artifact"] == f"main-releasability-dependency-health-{RUN_ID}"
        for receipt in receipts
    )


def test_renewal_rejects_non_exact_sha_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = guard.load_manifest()
    _install_github_payloads(monkeypatch, manifest, run=_run_payload(branch="main"))

    with pytest.raises(ValueError, match="not a successful governed exact-SHA"):
        renewal.renew_manifest(manifest, run_id=RUN_ID)


def test_renewal_rejects_failed_exact_revision_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = guard.load_manifest()
    _install_github_payloads(monkeypatch, manifest, jobs=_jobs_payload(conclusion="failure"))

    with pytest.raises(ValueError, match="successful exact revision assertion"):
        renewal.renew_manifest(manifest, run_id=RUN_ID)


def test_renewal_rejects_missing_required_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = guard.load_manifest()
    artifacts = _artifacts_payload(manifest)
    artifact_rows = artifacts["artifacts"]
    assert isinstance(artifact_rows, list)
    artifact_rows.pop()
    _install_github_payloads(monkeypatch, manifest, artifacts=artifacts)

    with pytest.raises(ValueError, match="GitHub artifact does not exist"):
        renewal.renew_manifest(manifest, run_id=RUN_ID)


def test_renewal_rejects_expired_required_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = guard.load_manifest()
    artifacts = _artifacts_payload(manifest)
    artifact_rows = artifacts["artifacts"]
    assert isinstance(artifact_rows, list)
    artifact_rows[0]["expires_at"] = "2000-01-01T00:00:00Z"
    _install_github_payloads(monkeypatch, manifest, artifacts=artifacts)

    with pytest.raises(ValueError, match="GitHub artifact is expired"):
        renewal.renew_manifest(manifest, run_id=RUN_ID)


def test_cli_writes_a_valid_renewed_manifest_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = guard.load_manifest()
    manifest_path = tmp_path / "pilot.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _install_github_payloads(monkeypatch, manifest)

    assert renewal.main(["--run-id", str(RUN_ID), "--manifest", str(manifest_path)]) == 0

    persisted = guard.load_manifest(manifest_path)
    assert persisted["assessment_date"] == manifest["assessment_date"]
    assert {receipt["event"] for _, receipt in guard._github_run_refs(persisted)} == {
        guard.RENEWABLE_RECEIPT_EVENT
    }
    assert not list(tmp_path.glob(".pilot.json.*.tmp"))
