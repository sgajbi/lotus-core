from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.quality import technology_governance_pilot_guard as guard


def _manifest() -> dict[str, object]:
    return guard.load_manifest()


def test_checked_in_pilot_manifest_is_complete_and_truthful() -> None:
    assert guard.validate_manifest(_manifest()) == []


def test_missing_and_duplicate_requirement_mappings_fail() -> None:
    manifest = copy.deepcopy(_manifest())
    mappings = manifest["dependency_artifacts"]
    assert isinstance(mappings, list)
    mappings.pop()
    mappings.append(copy.deepcopy(mappings[0]))

    errors = guard.validate_manifest(manifest)

    assert any("duplicate requirement mappings" in error for error in errors)
    assert any("missing requirements" in error for error in errors)


def test_missing_file_and_anchor_fail() -> None:
    manifest = copy.deepcopy(_manifest())
    mappings = manifest["dependency_artifacts"]
    assert isinstance(mappings, list)
    first = mappings[0]
    assert isinstance(first, dict)
    refs = first["evidence_refs"]
    assert isinstance(refs, list)
    refs[0]["path"] = "requirements/not-present.txt"
    refs[1]["anchors"] = ["not-present-anchor"]

    errors = guard.validate_manifest(manifest)

    assert any("evidence file does not exist" in error for error in errors)
    assert any("missing anchor" in error for error in errors)


@pytest.mark.parametrize("anchors", [[], [""], [" \n\t"]])
def test_empty_evidence_anchors_fail(anchors: list[str]) -> None:
    manifest = copy.deepcopy(_manifest())
    mappings = manifest["dependency_artifacts"]
    assert isinstance(mappings, list)
    mapping = mappings[0]
    assert isinstance(mapping, dict)
    refs = mapping["evidence_refs"]
    assert isinstance(refs, list)
    refs[0]["anchors"] = anchors

    errors = guard.validate_manifest(manifest)

    assert any("anchors must be non-empty strings" in error for error in errors)


def test_local_evidence_is_read_from_inspected_commit_not_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    evidence_path = repository / "evidence.txt"
    evidence_path.write_text("inspected authority\n", encoding="utf-8")
    subprocess.run(["git", "add", "evidence.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Lotus Test",
            "-c",
            "user.email=lotus-test@example.invalid",
            "commit",
            "-m",
            "evidence baseline",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    inspected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    evidence_path.write_text("current worktree drift\n", encoding="utf-8")

    inspected_errors: list[str] = []
    guard._validate_local_evidence(
        {"path": "evidence.txt", "anchors": ["inspected authority"]},
        root=repository,
        location="evidence",
        inspected_commit=inspected_commit,
        errors=inspected_errors,
    )
    drift_errors: list[str] = []
    guard._validate_local_evidence(
        {"path": "evidence.txt", "anchors": ["current worktree drift"]},
        root=repository,
        location="evidence",
        inspected_commit=inspected_commit,
        errors=drift_errors,
    )
    evidence_path.unlink()
    deleted_worktree_errors: list[str] = []
    guard._validate_local_evidence(
        {"path": "evidence.txt", "anchors": ["inspected authority"]},
        root=repository,
        location="evidence",
        inspected_commit=inspected_commit,
        errors=deleted_worktree_errors,
    )

    assert inspected_errors == []
    assert any("missing anchor" in error for error in drift_errors)
    assert deleted_worktree_errors == []


def test_actionable_posture_requires_canonical_issue() -> None:
    manifest = copy.deepcopy(_manifest())
    mappings = manifest["container_artifacts"]
    assert isinstance(mappings, list)
    mapping = mappings[1]
    assert isinstance(mapping, dict)
    mapping.pop("canonical_issue")

    errors = guard.validate_manifest(manifest)

    assert any("requires a canonical Core issue" in error for error in errors)


def test_report_only_manifest_cannot_make_release_or_product_claims() -> None:
    manifest = copy.deepcopy(_manifest())
    claims = manifest["claim_boundary"]
    assert isinstance(claims, dict)
    claims["release_certifying"] = True
    claims["production_ready_claim"] = True
    claims["bank_buyable_claim"] = True
    claims["supported_feature_claim"] = True

    errors = guard.validate_manifest(manifest)

    for claim in (
        "release_certifying",
        "production_ready_claim",
        "bank_buyable_claim",
        "supported_feature_claim",
    ):
        assert any(claim in error for error in errors)


def test_local_validation_pins_policy_identity_and_exception_control() -> None:
    manifest = copy.deepcopy(_manifest())
    policy_ref = manifest["policy_ref"]
    exception_control = manifest["exception_control"]
    assert isinstance(policy_ref, dict)
    assert isinstance(exception_control, dict)
    policy_ref["commit"] = "0" * 40
    exception_control["requirement_id"] = "inline_suppression"

    errors = guard.validate_manifest(manifest)

    assert any("policy_ref.commit must identify" in error for error in errors)
    assert any("must be exception_policy" in error for error in errors)


def test_github_run_evidence_is_numeric_and_bound_to_inspected_commit() -> None:
    manifest = copy.deepcopy(_manifest())
    mappings = manifest["dependency_artifacts"]
    assert isinstance(mappings, list)
    mapping = mappings[3]
    assert isinstance(mapping, dict)
    refs = mapping["evidence_refs"]
    assert isinstance(refs, list)
    run_ref = refs[1]
    run_ref["url"] = "https://github.com/sgajbi/lotus-core/actions/runs/not-a-run"
    run_ref["source_commit"] = "0" * 40

    errors = guard.validate_manifest(manifest)

    assert any("invalid Core GitHub run URL" in error for error in errors)
    assert any("must match inspected_core_commit" in error for error in errors)


def test_inspected_commit_must_resolve_in_core() -> None:
    manifest = copy.deepcopy(_manifest())
    manifest["inspected_core_commit"] = "f" * 40

    errors = guard.validate_manifest(manifest)

    assert any("must resolve to a Core commit" in error for error in errors)


def test_online_receipt_verification_rejects_missing_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    def github_payload(endpoint: str) -> dict[str, object]:
        if endpoint.endswith("artifacts?per_page=100"):
            return {"artifacts": []}
        return {
            "head_sha": manifest["inspected_core_commit"],
            "status": "completed",
            "conclusion": "success",
        }

    monkeypatch.setattr(guard, "_github_api_payload", github_payload)

    errors = guard.validate_manifest(manifest, verify_github=True)

    assert any("GitHub artifact does not exist" in error for error in errors)


def _write_platform_policy_repo(tmp_path: Path, policy: dict[str, object]) -> Path:
    platform_root = tmp_path / "lotus-platform"
    policy_path = (
        platform_root
        / "platform-contracts"
        / "technology-governance"
        / "lotus-technology-governance-policy.v1.json"
    )
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=platform_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=platform_root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Lotus Test",
            "-c",
            "user.email=lotus-test@example.invalid",
            "commit",
            "-m",
            "test policy",
        ],
        cwd=platform_root,
        check=True,
        capture_output=True,
    )
    return platform_root


def _minimal_policy() -> dict[str, object]:
    return {
        "contract_id": "lotus-platform-technology-governance-policy",
        "contract_version": "1.0.0",
        "lifecycle_status": "report_only",
        "dependency_evidence_policy": {
            "required_artifacts": sorted(guard.REQUIRED_COLLECTIONS["dependency_artifacts"])
        },
        "container_image_evidence_policy": {
            "required_identity_fields": sorted(
                guard.REQUIRED_COLLECTIONS["container_identity_fields"]
            ),
            "required_artifacts": sorted(guard.REQUIRED_COLLECTIONS["container_artifacts"]),
        },
        "vulnerability_severity_policy": [
            {"class": severity}
            for severity in sorted(guard.REQUIRED_COLLECTIONS["vulnerability_controls"])
        ],
        "rollout": {"lane_posture": "report_only", "pilot_repositories": ["lotus-core"]},
    }


def test_cross_repository_verification_accepts_exact_pinned_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_root = _write_platform_policy_repo(tmp_path, _minimal_policy())
    manifest = copy.deepcopy(_manifest())
    policy_ref = manifest["policy_ref"]
    assert isinstance(policy_ref, dict)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=platform_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    raw_policy = subprocess.run(
        ["git", "show", f"{commit}:{policy_ref['path']}"],
        cwd=platform_root,
        check=True,
        capture_output=True,
    ).stdout
    policy_ref["commit"] = commit
    policy_ref["document_sha256"] = hashlib.sha256(raw_policy).hexdigest()
    monkeypatch.setitem(guard.EXPECTED_POLICY_REF, "commit", commit)
    monkeypatch.setitem(guard.EXPECTED_POLICY_REF, "document_sha256", policy_ref["document_sha256"])

    assert guard.validate_manifest(manifest, platform_root=platform_root) == []


def test_cross_repository_verification_detects_policy_set_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _minimal_policy()
    dependency_policy = policy["dependency_evidence_policy"]
    assert isinstance(dependency_policy, dict)
    required = dependency_policy["required_artifacts"]
    assert isinstance(required, list)
    required.append("new_required_artifact")
    platform_root = _write_platform_policy_repo(tmp_path, policy)
    manifest = copy.deepcopy(_manifest())
    policy_ref = manifest["policy_ref"]
    assert isinstance(policy_ref, dict)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=platform_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    raw_policy = subprocess.run(
        ["git", "show", f"{commit}:{policy_ref['path']}"],
        cwd=platform_root,
        check=True,
        capture_output=True,
    ).stdout
    policy_ref["commit"] = commit
    policy_ref["document_sha256"] = hashlib.sha256(raw_policy).hexdigest()
    monkeypatch.setitem(guard.EXPECTED_POLICY_REF, "commit", commit)
    monkeypatch.setitem(guard.EXPECTED_POLICY_REF, "document_sha256", policy_ref["document_sha256"])

    errors = guard.validate_manifest(manifest, platform_root=platform_root)

    assert any("consumer projection drifted" in error for error in errors)


def test_cross_repository_verification_fails_closed_on_malformed_policy_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformed_policy = {
        "contract_id": "lotus-platform-technology-governance-policy",
        "contract_version": "1.0.0",
        "lifecycle_status": "report_only",
    }
    monkeypatch.setattr(
        guard,
        "_policy_bytes",
        lambda *_args, **_kwargs: json.dumps(malformed_policy).encode("utf-8"),
    )

    errors = guard.validate_manifest(_manifest(), platform_root=tmp_path)

    assert any("invalid required evidence shape" in error for error in errors)


def test_cross_repository_verification_rejects_non_object_rollout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformed_policy = _minimal_policy()
    malformed_policy["rollout"] = []
    monkeypatch.setattr(
        guard,
        "_policy_bytes",
        lambda *_args, **_kwargs: json.dumps(malformed_policy).encode("utf-8"),
    )

    errors = guard.validate_manifest(_manifest(), platform_root=tmp_path)

    assert any("rollout must be an object" in error for error in errors)
