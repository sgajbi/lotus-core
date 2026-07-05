"""Write a governed image release manifest for an immutable container image."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "lotus-core.image-release-manifest.v1"


def _bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got {value!r}")


def _digest_image_ref(image_ref: str, image_digest: str) -> str:
    if not image_digest.startswith("sha256:"):
        raise SystemExit("image digest must start with sha256:")
    return f"{image_ref}@{image_digest}"


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
    ci_pipeline_run_id: str,
    sbom_generated: bool,
    vulnerability_scan_status: str,
    image_signed: bool,
    provenance_attestation_generated: bool,
    kubernetes_deploys_by_digest: bool,
    promotion_environments: list[str],
) -> dict[str, object]:
    digest_ref = _digest_image_ref(image_ref, image_digest)
    promotions = [
        {"environment": environment, "image_ref": digest_ref}
        for environment in promotion_environments
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
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
        "ci_pipeline_run_id": ci_pipeline_run_id,
        "sbom_generated": sbom_generated,
        "vulnerability_scan_status": vulnerability_scan_status,
        "image_signed": image_signed,
        "provenance_attestation_generated": provenance_attestation_generated,
        "kubernetes_deploys_by_digest": kubernetes_deploys_by_digest,
        "same_image_promoted_across_environments": all(
            promotion["image_ref"] == digest_ref for promotion in promotions
        ),
        "promotions": promotions,
        "runtime_env": {
            "LOTUS_GIT_COMMIT_SHA": git_commit_sha,
            "LOTUS_GIT_BRANCH": git_branch,
            "LOTUS_BUILD_TIMESTAMP": build_timestamp,
            "LOTUS_REPO_URL": repo_url,
            "LOTUS_IMAGE_VERSION": image_version,
            "LOTUS_IMAGE_DIGEST": image_digest,
            "LOTUS_CI_RUN_ID": ci_pipeline_run_id,
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
    parser.add_argument("--ci-pipeline-run-id", required=True)
    parser.add_argument("--sbom-generated", required=True, type=_bool_arg)
    parser.add_argument("--vulnerability-scan-status", required=True)
    parser.add_argument("--image-signed", required=True, type=_bool_arg)
    parser.add_argument("--provenance-attestation-generated", required=True, type=_bool_arg)
    parser.add_argument("--kubernetes-deploys-by-digest", required=True, type=_bool_arg)
    parser.add_argument("--promotion-environments", nargs="+", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_release_manifest(
        service=args.service,
        image_name=args.image_name,
        image_ref=args.image_ref,
        image_tag=args.image_tag,
        image_digest=args.image_digest,
        git_commit_sha=args.git_commit_sha,
        git_branch=args.git_branch,
        image_version=args.image_version,
        build_timestamp=args.build_timestamp,
        repo_url=args.repo_url,
        ci_pipeline_run_id=args.ci_pipeline_run_id,
        sbom_generated=args.sbom_generated,
        vulnerability_scan_status=args.vulnerability_scan_status,
        image_signed=args.image_signed,
        provenance_attestation_generated=args.provenance_attestation_generated,
        kubernetes_deploys_by_digest=args.kubernetes_deploys_by_digest,
        promotion_environments=list(args.promotion_environments),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
