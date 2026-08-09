"""Validate the report-only Lotus Core technology-governance pilot evidence map."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT
    / "contracts"
    / "technology-governance"
    / "lotus-core-technology-governance-pilot.v1.json"
)

SCHEMA_VERSION = "lotus-core.technology-governance-pilot.v1"
PILOT_ID = "lotus-core-technology-governance-pilot"
GITHUB_REPOSITORY = "sgajbi/lotus-core"
CLASSIFICATIONS = {"present", "gap", "non_certifying"}
CORE_ISSUE_PATTERN = re.compile(r"^https://github\.com/sgajbi/lotus-core/issues/\d+$")
CORE_RUN_PATTERN = re.compile(r"^https://github\.com/sgajbi/lotus-core/actions/runs/\d+$")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_WORKFLOW_ID = 259248882
RECEIPT_WORKFLOW_PATH = ".github/workflows/main-releasability.yml"
RECEIPT_EVENT = "push"
RECEIPT_BRANCH = "main"
EPHEMERAL_RECEIPT_ARTIFACTS = {"main-runtime-image-set"}
EXPECTED_POLICY_REF = {
    "repository": "sgajbi/lotus-platform",
    "commit": "c3af9ace58f54fb070db32d2b428ff79c852d818",
    "path": "platform-contracts/technology-governance/lotus-technology-governance-policy.v1.json",
    "document_sha256": "4b907525b965afb423f2d72de818dcf20eed2c2210d8db40b65d7761b9e3ca4f",
    "contract_id": "lotus-platform-technology-governance-policy",
    "contract_version": "1.0.0",
    "lifecycle_status": "report_only",
}

# This is the bounded consumer projection of policy v1. Cross-repository mode proves
# that it remains exactly aligned to the pinned Platform policy document.
REQUIRED_COLLECTIONS = {
    "dependency_artifacts": {
        "direct_dependency_manifest",
        "locked_manifest",
        "transitive_dependency_inventory",
        "runtime_sbom",
        "license_inventory",
        "vulnerability_scan",
        "provenance_or_generator_version",
    },
    "container_identity_fields": {
        "image_repository",
        "image_digest",
        "git_sha",
        "source_repository",
        "build_pipeline",
        "build_timestamp",
        "architecture",
    },
    "container_artifacts": {
        "oci_labels",
        "image_sbom",
        "signature",
        "provenance_attestation",
        "scan_receipt",
        "base_image_support_evidence",
        "runtime_smoke_receipt",
    },
    "vulnerability_controls": {"known_exploited", "critical", "high", "medium", "low"},
}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pilot manifest must be a JSON object")
    return payload


@lru_cache(maxsize=None)
def _git_file_content(root: Path, commit: str, evidence_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{evidence_path}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(evidence_path)
    return result.stdout


def _validate_local_evidence(
    evidence: dict[str, Any],
    *,
    root: Path,
    location: str,
    inspected_commit: str,
    errors: list[str],
) -> None:
    evidence_path = evidence.get("path")
    if not isinstance(evidence_path, str) or not evidence_path:
        errors.append(f"{location}: local_file evidence requires path")
        return
    candidate = (root / evidence_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{location}: evidence path escapes repository root: {evidence_path}")
        return
    anchors = evidence.get("anchors", [])
    if (
        not isinstance(anchors, list)
        or not anchors
        or not all(isinstance(anchor, str) and anchor.strip() for anchor in anchors)
    ):
        errors.append(f"{location}: anchors must be non-empty strings")
        return
    try:
        content = _git_file_content(root, inspected_commit, evidence_path)
    except ValueError:
        errors.append(
            f"{location}: evidence file does not exist at inspected_core_commit: {evidence_path}"
        )
        return
    for anchor in anchors:
        if anchor not in content:
            errors.append(f"{location}: {evidence_path} is missing anchor {anchor!r}")


def _validate_evidence_refs(
    refs: Any,
    *,
    root: Path,
    location: str,
    inspected_commit: str,
    errors: list[str],
) -> None:
    if not isinstance(refs, list):
        errors.append(f"{location}: evidence_refs must be an array")
        return
    for index, evidence in enumerate(refs):
        ref_location = f"{location}.evidence_refs[{index}]"
        if not isinstance(evidence, dict):
            errors.append(f"{ref_location}: evidence reference must be an object")
            continue
        kind = evidence.get("kind")
        if kind == "local_file":
            _validate_local_evidence(
                evidence,
                root=root,
                location=ref_location,
                inspected_commit=inspected_commit,
                errors=errors,
            )
        elif kind == "github_run":
            _validate_github_run_evidence(
                evidence,
                location=ref_location,
                inspected_commit=inspected_commit,
                errors=errors,
            )
        else:
            errors.append(f"{ref_location}: unsupported evidence kind {kind!r}")


def _validate_github_run_evidence(
    evidence: dict[str, Any],
    *,
    location: str,
    inspected_commit: str,
    errors: list[str],
) -> None:
    url = evidence.get("url")
    source_commit = evidence.get("source_commit")
    artifact = evidence.get("artifact")
    artifact_digest = evidence.get("artifact_digest")
    if not isinstance(url, str) or not CORE_RUN_PATTERN.fullmatch(url):
        errors.append(f"{location}: invalid Core GitHub run URL")
    if not isinstance(source_commit, str) or not FULL_SHA_PATTERN.fullmatch(source_commit):
        errors.append(f"{location}: source_commit must be a full Git SHA")
    elif source_commit != inspected_commit:
        errors.append(f"{location}: source_commit must match inspected_core_commit")
    if not isinstance(artifact, str) or not artifact:
        errors.append(f"{location}: GitHub run evidence requires artifact")
    elif artifact in EPHEMERAL_RECEIPT_ARTIFACTS:
        errors.append(f"{location}: ephemeral artifact cannot be a durable governance receipt")
    if not isinstance(artifact_digest, str) or not ARTIFACT_DIGEST_PATTERN.fullmatch(
        artifact_digest
    ):
        errors.append(f"{location}: artifact_digest must be a SHA-256 artifact digest")
    if evidence.get("workflow_id") != RECEIPT_WORKFLOW_ID:
        errors.append(f"{location}: workflow_id must identify Main Releasability Gate")
    if evidence.get("workflow_path") != RECEIPT_WORKFLOW_PATH:
        errors.append(f"{location}: workflow_path must identify Main Releasability Gate")
    if evidence.get("event") != RECEIPT_EVENT:
        errors.append(f"{location}: GitHub run event must be push")
    if evidence.get("head_branch") != RECEIPT_BRANCH:
        errors.append(f"{location}: GitHub run head_branch must be main")


def _validate_mapping(
    mapping: Any,
    *,
    root: Path,
    location: str,
    inspected_commit: str,
    errors: list[str],
) -> None:
    if not isinstance(mapping, dict):
        errors.append(f"{location}: mapping must be an object")
        return
    classification = mapping.get("classification")
    if classification not in CLASSIFICATIONS:
        errors.append(f"{location}: unsupported classification {classification!r}")
    rationale = mapping.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append(f"{location}: rationale is required")
    refs = mapping.get("evidence_refs")
    _validate_evidence_refs(
        refs,
        root=root,
        location=location,
        inspected_commit=inspected_commit,
        errors=errors,
    )
    if classification == "present" and not refs:
        errors.append(f"{location}: present evidence requires at least one reference")
    if classification in {"gap", "non_certifying"}:
        issue = mapping.get("canonical_issue")
        if not isinstance(issue, str) or not CORE_ISSUE_PATTERN.fullmatch(issue):
            errors.append(f"{location}: actionable posture requires a canonical Core issue")


def _validate_collection(
    manifest: dict[str, Any],
    *,
    name: str,
    root: Path,
    inspected_commit: str,
    errors: list[str],
) -> None:
    mappings = manifest.get(name)
    if not isinstance(mappings, list):
        errors.append(f"{name}: must be an array")
        return
    identifiers: list[str] = []
    for index, mapping in enumerate(mappings):
        location = f"{name}[{index}]"
        _validate_mapping(
            mapping,
            root=root,
            location=location,
            inspected_commit=inspected_commit,
            errors=errors,
        )
        if isinstance(mapping, dict) and isinstance(mapping.get("requirement_id"), str):
            identifiers.append(mapping["requirement_id"])
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        errors.append(f"{name}: duplicate requirement mappings: {', '.join(duplicates)}")
    expected = REQUIRED_COLLECTIONS[name]
    actual = set(identifiers)
    if missing := expected - actual:
        errors.append(f"{name}: missing requirements: {', '.join(sorted(missing))}")
    if unexpected := actual - expected:
        errors.append(f"{name}: unexpected requirements: {', '.join(sorted(unexpected))}")


def _policy_bytes(platform_root: Path, *, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=platform_root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cannot load pinned Platform policy: {detail}")
    return result.stdout


def _validate_platform_policy(
    manifest: dict[str, Any], *, platform_root: Path, errors: list[str]
) -> None:
    policy_ref = manifest["policy_ref"]
    try:
        raw_policy = _policy_bytes(
            platform_root,
            commit=policy_ref["commit"],
            path=policy_ref["path"],
        )
        policy = json.loads(raw_policy)
    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return
    actual_digest = hashlib.sha256(raw_policy).hexdigest()
    if actual_digest != policy_ref["document_sha256"]:
        errors.append("policy_ref.document_sha256 does not match the pinned Platform policy")
    for key in ("contract_id", "contract_version", "lifecycle_status"):
        if policy.get(key) != policy_ref.get(key):
            errors.append(f"policy_ref.{key} does not match the pinned Platform policy")
    try:
        policy_collections = {
            "dependency_artifacts": set(policy["dependency_evidence_policy"]["required_artifacts"]),
            "container_identity_fields": set(
                policy["container_image_evidence_policy"]["required_identity_fields"]
            ),
            "container_artifacts": set(
                policy["container_image_evidence_policy"]["required_artifacts"]
            ),
            "vulnerability_controls": {
                entry["class"] for entry in policy["vulnerability_severity_policy"]
            },
        }
        rollout = policy["rollout"]
        if not isinstance(rollout, dict):
            raise TypeError("rollout must be an object")
    except (KeyError, TypeError) as exc:
        errors.append(f"pinned Platform policy has invalid required evidence shape: {exc}")
        return
    for name, required in policy_collections.items():
        if required != REQUIRED_COLLECTIONS[name]:
            errors.append(f"{name}: local consumer projection drifted from pinned Platform policy")
    if rollout.get("lane_posture") != "report_only":
        errors.append("pinned Platform pilot lane is not report_only")
    if "lotus-core" not in rollout.get("pilot_repositories", []):
        errors.append("pinned Platform policy does not include lotus-core as a pilot")


def _validate_manifest_identity(manifest: dict[str, Any], *, root: Path, errors: list[str]) -> str:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("pilot_id") != PILOT_ID:
        errors.append(f"pilot_id must be {PILOT_ID}")
    if not CORE_ISSUE_PATTERN.fullmatch(str(manifest.get("governed_by_issue", ""))):
        errors.append("governed_by_issue must be a canonical Core issue URL")
    try:
        date.fromisoformat(str(manifest["assessment_date"]))
    except (KeyError, ValueError):
        errors.append("assessment_date must be an ISO date")
    inspected_commit = manifest.get("inspected_core_commit")
    if not isinstance(inspected_commit, str) or not FULL_SHA_PATTERN.fullmatch(inspected_commit):
        errors.append("inspected_core_commit must be a full Git SHA")
        return ""
    if not _git_commit_resolves(root, inspected_commit):
        errors.append("inspected_core_commit must resolve to a Core commit")
    elif not _git_commit_is_on_main(root, inspected_commit):
        errors.append("inspected_core_commit must be an ancestor of the governed main ref")
    return inspected_commit


def _git_commit_resolves(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _git_commit_is_on_main(root: Path, commit: str) -> bool:
    main_ref = _resolve_main_ref(root)
    if main_ref is None:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, main_ref],
        cwd=root,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _resolve_main_ref(root: Path) -> str | None:
    for candidate in ("refs/remotes/origin/main", "refs/heads/main"):
        result = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", candidate],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return candidate
    return None


def _validate_policy_ref(manifest: dict[str, Any], errors: list[str]) -> dict[str, Any] | None:
    policy_ref = manifest.get("policy_ref")
    if not isinstance(policy_ref, dict):
        errors.append("policy_ref must be an object")
        return None
    for field, expected in EXPECTED_POLICY_REF.items():
        if policy_ref.get(field) != expected:
            errors.append(f"policy_ref.{field} must identify the pinned Platform policy")
    if not FULL_SHA_PATTERN.fullmatch(str(policy_ref.get("commit", ""))):
        errors.append("policy_ref.commit must be a full Git SHA")
    if not SHA256_PATTERN.fullmatch(str(policy_ref.get("document_sha256", ""))):
        errors.append("policy_ref.document_sha256 must be a SHA-256 digest")
    if policy_ref.get("lifecycle_status") != "report_only":
        errors.append("policy_ref.lifecycle_status must remain report_only")
    return policy_ref


def _validate_claim_boundary(manifest: dict[str, Any], errors: list[str]) -> None:
    claims = manifest.get("claim_boundary")
    if not isinstance(claims, dict) or claims.get("lane_posture") != "report_only":
        errors.append("claim_boundary must declare report_only lane posture")
        return
    for claim in (
        "release_certifying",
        "production_ready_claim",
        "bank_buyable_claim",
        "supported_feature_claim",
    ):
        if claims.get(claim) is not False:
            errors.append(f"claim_boundary.{claim} must be false")


def _validate_technology_assessment(manifest: dict[str, Any], errors: list[str]) -> None:
    assessment = manifest.get("technology_state_assessment")
    if not isinstance(assessment, dict) or assessment.get("classification") != "non_certifying":
        errors.append("technology_state_assessment must remain non_certifying")
        return
    issues = assessment.get("canonical_issues")
    if (
        not isinstance(issues, list)
        or not issues
        or not all(
            isinstance(issue, str) and CORE_ISSUE_PATTERN.fullmatch(issue) for issue in issues
        )
    ):
        errors.append("technology_state_assessment requires canonical Core issues")


def _validate_exception_control(
    manifest: dict[str, Any], *, root: Path, inspected_commit: str, errors: list[str]
) -> None:
    exception_control = manifest.get("exception_control")
    _validate_mapping(
        exception_control,
        root=root,
        location="exception_control",
        inspected_commit=inspected_commit,
        errors=errors,
    )
    if (
        not isinstance(exception_control, dict)
        or exception_control.get("requirement_id") != "exception_policy"
    ):
        errors.append("exception_control.requirement_id must be exception_policy")


@lru_cache(maxsize=None)
def _github_api_payload(endpoint: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ValueError(f"cannot execute GitHub CLI: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or "GitHub API request failed"
        raise ValueError(detail)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GitHub API returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("GitHub API response must be an object")
    return payload


def _github_run_refs(manifest: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    mappings: list[Any] = []
    for collection_name in REQUIRED_COLLECTIONS:
        collection = manifest.get(collection_name)
        if isinstance(collection, list):
            mappings.extend(collection)
    mappings.append(manifest.get("exception_control"))
    for mapping_index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            continue
        refs = mapping.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        for ref_index, evidence in enumerate(refs):
            if isinstance(evidence, dict) and evidence.get("kind") == "github_run":
                yield f"github_receipts[{mapping_index}].evidence_refs[{ref_index}]", evidence


def _validate_github_receipt(evidence: dict[str, Any], *, location: str, errors: list[str]) -> None:
    url = evidence.get("url")
    if not isinstance(url, str) or not CORE_RUN_PATTERN.fullmatch(url):
        return
    run_id = url.rsplit("/", maxsplit=1)[-1]
    try:
        run = _github_api_payload(f"repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}")
        artifacts_payload = _github_api_payload(
            f"repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"
        )
    except ValueError as exc:
        errors.append(f"{location}: GitHub receipt lookup failed: {exc}")
        return
    if run.get("head_sha") != evidence.get("source_commit"):
        errors.append(f"{location}: GitHub run head SHA does not match source_commit")
    if run.get("workflow_id") != evidence.get("workflow_id"):
        errors.append(f"{location}: GitHub run workflow ID does not match evidence")
    if run.get("path") != evidence.get("workflow_path"):
        errors.append(f"{location}: GitHub run workflow path does not match evidence")
    if run.get("event") != evidence.get("event"):
        errors.append(f"{location}: GitHub run event does not match evidence")
    if run.get("head_branch") != evidence.get("head_branch"):
        errors.append(f"{location}: GitHub run head branch does not match evidence")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append(f"{location}: GitHub run is not completed successfully")
    artifacts = artifacts_payload.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append(f"{location}: GitHub artifact response is malformed")
        return
    artifact_name = evidence.get("artifact")
    matches = [artifact for artifact in artifacts if artifact.get("name") == artifact_name]
    if not matches:
        errors.append(f"{location}: GitHub artifact does not exist: {artifact_name}")
    elif all(bool(artifact.get("expired")) for artifact in matches):
        errors.append(f"{location}: GitHub artifact is expired: {artifact_name}")
    elif not any(
        not bool(artifact.get("expired"))
        and artifact.get("digest") == evidence.get("artifact_digest")
        for artifact in matches
    ):
        errors.append(f"{location}: GitHub artifact digest does not match evidence")


def _validate_github_receipts(manifest: dict[str, Any], errors: list[str]) -> None:
    for location, evidence in _github_run_refs(manifest):
        _validate_github_receipt(evidence, location=location, errors=errors)


def validate_manifest(
    manifest: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
    platform_root: Path | None = None,
    verify_github: bool = False,
) -> list[str]:
    errors: list[str] = []
    inspected_commit = _validate_manifest_identity(manifest, root=root, errors=errors)
    policy_ref = _validate_policy_ref(manifest, errors)
    _validate_claim_boundary(manifest, errors)
    _validate_technology_assessment(manifest, errors)
    for collection_name in REQUIRED_COLLECTIONS:
        _validate_collection(
            manifest,
            name=collection_name,
            root=root,
            inspected_commit=inspected_commit,
            errors=errors,
        )
    _validate_exception_control(
        manifest,
        root=root,
        inspected_commit=inspected_commit,
        errors=errors,
    )
    if platform_root is not None and isinstance(policy_ref, dict):
        _validate_platform_policy(manifest, platform_root=platform_root, errors=errors)
    if verify_github:
        _validate_github_receipts(manifest, errors)
    return errors


def _git_value(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--platform-root", type=Path)
    parser.add_argument(
        "--verify-github",
        action="store_true",
        help=(
            "Verify cited run conclusions, source SHAs, artifact existence, and expiry via GitHub."
        ),
    )
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Technology-governance pilot guard failed: {exc}")
        return 1
    errors = validate_manifest(
        manifest,
        root=REPO_ROOT,
        platform_root=args.platform_root.resolve() if args.platform_root else None,
        verify_github=args.verify_github,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    head = _git_value(REPO_ROOT, "rev-parse", "HEAD")
    tree = _git_value(REPO_ROOT, "rev-parse", "HEAD^{tree}")
    dirty = bool(_git_value(REPO_ROOT, "status", "--porcelain"))
    print(
        json.dumps(
            {
                "status": "passed",
                "lane_posture": "report_only",
                "core_head": head,
                "core_tree": tree,
                "worktree_dirty": dirty,
                "inspected_core_commit": manifest["inspected_core_commit"],
                "platform_policy_commit": manifest["policy_ref"]["commit"],
                "release_certifying": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
