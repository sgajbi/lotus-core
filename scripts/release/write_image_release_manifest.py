"""Write a governed candidate manifest from verified immutable image evidence."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.release.image_release_evidence import (
    base_image_evidence_identity,
    provenance_verification_identity,
    sbom_identity,
    scan_receipt_identity,
    signature_verification_identity,
)
from scripts.release.vulnerability_authority_bundle import (
    load_vulnerability_authority_identity,
)

SCHEMA_VERSION = "lotus-core.image-release-manifest.v2"
FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_PROMOTION_ENVIRONMENTS = ("dev", "uat", "prod")

OCI_METADATA_LABELS = {
    "org.opencontainers.image.revision": "git_commit_sha",
    "org.opencontainers.image.ref.name": "git_branch",
    "org.opencontainers.image.created": "build_timestamp",
    "org.opencontainers.image.source": "repo_url",
    "org.opencontainers.image.version": "image_version",
    "org.opencontainers.image.ci.run_id": "ci_pipeline_run_id",
}


def _digest_image_ref(image_ref: str, image_digest: str) -> str:
    if not SHA256_PATTERN.fullmatch(image_digest):
        raise SystemExit("image digest must be a sha256 digest with 64 hexadecimal characters")
    return f"{image_ref}@{image_digest}"


def _require_release_identity(
    *,
    image_tag: str,
    git_commit_sha: str,
    git_branch: str,
    image_version: str,
    image_digest: str,
    build_timestamp: str,
    repo_url: str,
    ci_pipeline_run_id: str,
    ci_run_attempt: str,
) -> None:
    if not FULL_GIT_SHA_PATTERN.fullmatch(git_commit_sha):
        raise SystemExit("git commit SHA must be a full 40-character lowercase hexadecimal SHA")
    for field_name, field_value in {
        "git branch": git_branch,
        "build timestamp": build_timestamp,
        "repo URL": repo_url,
        "CI pipeline run ID": ci_pipeline_run_id,
        "CI run attempt": ci_run_attempt,
    }.items():
        if not field_value.strip() or field_value == "unknown":
            raise SystemExit(f"{field_name} is required")
    if not ci_pipeline_run_id.isdecimal() or not ci_run_attempt.isdecimal():
        raise SystemExit("CI run identity must use positive integers")
    if int(ci_pipeline_run_id) < 1 or int(ci_run_attempt) < 1:
        raise SystemExit("CI run identity must use positive integers")
    if not image_tag.endswith(f":{git_commit_sha}"):
        raise SystemExit("image tag must be the Git commit SHA tag")
    if image_version != git_commit_sha:
        raise SystemExit("image version must match the Git commit SHA")
    if not repo_url.startswith(("https://", "git@")):
        raise SystemExit("repo URL must be an HTTPS or SSH repository URL")
    _digest_image_ref("subject", image_digest)


def _subject(evidence: dict[str, Any]) -> dict[str, Any] | None:
    value = evidence.get("subject")
    return value if isinstance(value, dict) else None


def _require_evidence_subjects(
    *,
    service: str,
    image_ref: str,
    image_digest: str,
    scan_receipt: dict[str, Any],
    sbom: dict[str, Any],
    signature_verification: dict[str, Any],
    provenance_verification: dict[str, Any],
) -> None:
    expected_image = {"image_ref": image_ref, "image_digest": image_digest}
    expected_scan = {
        "service": service,
        **expected_image,
        "digest_image_ref": f"{image_ref}@{image_digest}",
    }
    if _subject(scan_receipt) != expected_scan:
        raise SystemExit("scan receipt does not bind the release subject")
    for name, evidence in (
        ("SBOM", sbom),
        ("signature verification", signature_verification),
        ("provenance verification", provenance_verification),
    ):
        if _subject(evidence) != expected_image:
            raise SystemExit(f"{name} does not bind the release subject")


def _validated_promotions(
    receipts: list[dict[str, Any]], *, digest_image_ref: str
) -> list[dict[str, str]]:
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for receipt in receipts:
        environment = receipt.get("environment")
        image_ref = receipt.get("image_ref")
        receipt_sha256 = receipt.get("receipt_sha256")
        if environment not in REQUIRED_PROMOTION_ENVIRONMENTS or environment in seen:
            raise SystemExit("promotion receipt environment is invalid or duplicated")
        if image_ref != digest_image_ref:
            raise SystemExit("promotion receipt does not bind the release digest")
        if not isinstance(receipt_sha256, str) or not SHA256_PATTERN.fullmatch(receipt_sha256):
            raise SystemExit("promotion receipt digest is invalid")
        seen.add(environment)
        validated.append(
            {
                "environment": environment,
                "image_ref": image_ref,
                "receipt_sha256": receipt_sha256,
            }
        )
    return sorted(
        validated, key=lambda item: REQUIRED_PROMOTION_ENVIRONMENTS.index(item["environment"])
    )


def build_release_manifest(
    *,
    service: str,
    image_name: str,
    image_ref: str,
    image_tag: str,
    image_digest: str,
    git_commit_sha: str,
    git_branch: str,
    image_version: str,
    build_timestamp: str,
    repo_url: str,
    repository: str,
    ci_pipeline_run_id: str,
    ci_run_attempt: str,
    scan_receipt: dict[str, Any],
    sbom: dict[str, Any],
    signature_verification: dict[str, Any],
    provenance_verification: dict[str, Any],
    base_image: dict[str, Any],
    promotion_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Build a candidate manifest only from independently validated evidence."""
    _require_release_identity(
        image_tag=image_tag,
        git_commit_sha=git_commit_sha,
        git_branch=git_branch,
        image_version=image_version,
        image_digest=image_digest,
        build_timestamp=build_timestamp,
        repo_url=repo_url,
        ci_pipeline_run_id=ci_pipeline_run_id,
        ci_run_attempt=ci_run_attempt,
    )
    _require_evidence_subjects(
        service=service,
        image_ref=image_ref,
        image_digest=image_digest,
        scan_receipt=scan_receipt,
        sbom=sbom,
        signature_verification=signature_verification,
        provenance_verification=provenance_verification,
    )
    source = scan_receipt.get("source")
    if source != {
        "repository": repository,
        "git_commit_sha": git_commit_sha,
        "ci_run_id": ci_pipeline_run_id,
        "ci_run_attempt": ci_run_attempt,
    }:
        raise SystemExit("scan receipt does not bind the release source")
    policy = scan_receipt.get("policy")
    if not isinstance(policy, dict) or policy.get("decision") != "passed":
        raise SystemExit("scan receipt does not contain a passed decision")

    digest_ref = _digest_image_ref(image_ref, image_digest)
    promotions = _validated_promotions(promotion_receipts or [], digest_image_ref=digest_ref)
    promoted_environments = {item["environment"] for item in promotions}
    promotion_complete = set(REQUIRED_PROMOTION_ENVIRONMENTS).issubset(promoted_environments)
    runtime_env = {
        "LOTUS_GIT_COMMIT_SHA": git_commit_sha,
        "LOTUS_GIT_BRANCH": git_branch,
        "LOTUS_BUILD_TIMESTAMP": build_timestamp,
        "LOTUS_REPO_URL": repo_url,
        "LOTUS_IMAGE_VERSION": image_version,
        "LOTUS_CI_RUN_ID": ci_pipeline_run_id,
    }
    metadata_values = {
        "git_commit_sha": git_commit_sha,
        "git_branch": git_branch,
        "build_timestamp": build_timestamp,
        "repo_url": repo_url,
        "image_version": image_version,
        "ci_pipeline_run_id": ci_pipeline_run_id,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "release_posture": "promoted" if promotion_complete else "candidate",
        "release_eligible": True,
        "promotion_eligible": True,
        "service": service,
        "image_name": image_name,
        "image_ref": image_ref,
        "image_tag": image_tag,
        "image_digest": image_digest,
        "digest_image_ref": digest_ref,
        "git_commit_sha": git_commit_sha,
        "git_branch": git_branch,
        "image_version": image_version,
        "build_timestamp": build_timestamp,
        "repo_url": repo_url,
        "repository": repository,
        "ci_pipeline_run_id": ci_pipeline_run_id,
        "ci_run_attempt": ci_run_attempt,
        "evidence": {
            "vulnerability_scan": scan_receipt,
            "sbom": sbom,
            "signature_verification": signature_verification,
            "provenance_verification": provenance_verification,
            "base_image": base_image,
        },
        # Compatibility fields are derived from validated evidence, never CLI assertions.
        "sbom_generated": True,
        "vulnerability_scan_status": "passed",
        "image_signed": True,
        "provenance_attestation_generated": True,
        "kubernetes_deploys_by_digest": promotion_complete,
        "same_image_promoted_across_environments": promotion_complete,
        "promotions": promotions,
        "runtime_env": runtime_env,
        "oci_labels": {
            label_name: metadata_values[field_name]
            for label_name, field_name in OCI_METADATA_LABELS.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--image-name", required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--git-commit-sha", required=True)
    parser.add_argument("--git-branch", required=True)
    parser.add_argument("--image-version", required=True)
    parser.add_argument("--build-timestamp", required=True)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ci-pipeline-run-id", required=True)
    parser.add_argument("--ci-run-attempt", required=True)
    parser.add_argument("--scan-receipt", required=True, type=Path)
    parser.add_argument("--authority-bundle", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--signature-verification", required=True, type=Path)
    parser.add_argument("--provenance-verification", required=True, type=Path)
    parser.add_argument("--certificate-issuer", required=True)
    parser.add_argument("--certificate-subject-pattern", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--base-lifecycle-inventory", required=True, type=Path)
    parser.add_argument("--base-manifest-evidence", required=True, type=Path)
    parser.add_argument("--dockerfile", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    authority = load_vulnerability_authority_identity(
        args.authority_bundle,
        expected_repository=args.repository,
        expected_git_commit_sha=args.git_commit_sha,
        expected_ci_run_id=args.ci_pipeline_run_id,
        expected_ci_run_attempt=args.ci_run_attempt,
    )
    common_subject = {"image_ref": args.image_ref, "image_digest": args.image_digest}
    sbom = sbom_identity(args.sbom, **common_subject)
    scan = scan_receipt_identity(
        args.scan_receipt,
        service=args.service,
        repository=args.repository,
        git_commit_sha=args.git_commit_sha,
        ci_run_id=args.ci_pipeline_run_id,
        ci_run_attempt=args.ci_run_attempt,
        vulnerability_authority=authority,
        **common_subject,
    )
    manifest = build_release_manifest(
        service=args.service,
        image_name=args.image_name,
        image_tag=args.image_tag,
        git_commit_sha=args.git_commit_sha,
        git_branch=args.git_branch,
        image_version=args.image_version,
        build_timestamp=args.build_timestamp,
        repo_url=args.repo_url,
        repository=args.repository,
        ci_pipeline_run_id=args.ci_pipeline_run_id,
        ci_run_attempt=args.ci_run_attempt,
        scan_receipt=scan,
        sbom=sbom,
        signature_verification=signature_verification_identity(
            args.signature_verification,
            expected_issuer=args.certificate_issuer,
            expected_subject_pattern=args.certificate_subject_pattern,
            **common_subject,
        ),
        provenance_verification=provenance_verification_identity(
            args.provenance_verification,
            repository=args.repository,
            git_commit_sha=args.git_commit_sha,
            workflow_ref=args.workflow_ref,
            service=args.service,
            dockerfile=args.dockerfile,
            ci_run_id=args.ci_pipeline_run_id,
            ci_run_attempt=args.ci_run_attempt,
            sbom_sha256=str(sbom["sha256"]),
            **common_subject,
        ),
        base_image=base_image_evidence_identity(
            inventory_path=args.base_lifecycle_inventory,
            manifest_path=args.base_manifest_evidence,
            dockerfile_path=args.dockerfile,
        ),
        **common_subject,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
