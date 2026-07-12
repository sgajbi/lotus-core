"""Render the transaction-processing Kubernetes deployment from release evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, cast

TARGET_SERVICE = "portfolio_transaction_processing_service"
TARGET_IMAGE_NAME = "portfolio-transaction-processing-service"
PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)
PLACEHOLDER_IMAGE_REF = (
    "ghcr.io/sgajbi/lotus-core/portfolio-transaction-processing-service@" + PLACEHOLDER_DIGEST
)
DIGEST_IMAGE_PATTERN = re.compile(r"^ghcr\.io/sgajbi/lotus-core/.+@sha256:[0-9a-f]{64}$")


class DeploymentRenderError(ValueError):
    """Raised when release evidence cannot authorize an immutable deployment."""


def release_image_ref(manifest: dict[str, Any]) -> str:
    if manifest.get("service") != TARGET_SERVICE:
        raise DeploymentRenderError("release manifest does not belong to the target service")
    if manifest.get("image_name") != TARGET_IMAGE_NAME:
        raise DeploymentRenderError("release manifest has an unexpected image name")
    required_truth = {
        "sbom_generated": True,
        "vulnerability_scan_status": "passed",
        "image_signed": True,
        "provenance_attestation_generated": True,
        "kubernetes_deploys_by_digest": True,
        "same_image_promoted_across_environments": True,
    }
    for field, expected in required_truth.items():
        if manifest.get(field) != expected:
            raise DeploymentRenderError(f"release manifest does not prove {field}={expected!r}")

    digest_image_ref = manifest.get("digest_image_ref")
    if not isinstance(digest_image_ref, str) or not DIGEST_IMAGE_PATTERN.fullmatch(
        digest_image_ref
    ):
        raise DeploymentRenderError("release manifest has an invalid digest image reference")
    if not digest_image_ref.endswith(f"@{manifest.get('image_digest')}"):
        raise DeploymentRenderError("release digest and digest image reference differ")

    promotions = manifest.get("promotions")
    if not isinstance(promotions, list):
        raise DeploymentRenderError("release manifest promotions are missing")
    promotion_refs = {
        item.get("image_ref")
        for item in promotions
        if isinstance(item, dict) and item.get("environment") in {"dev", "uat", "prod"}
    }
    promotion_environments = {
        item.get("environment") for item in promotions if isinstance(item, dict)
    }
    if not {"dev", "uat", "prod"}.issubset(promotion_environments):
        raise DeploymentRenderError("release manifest does not cover dev, uat, and prod")
    if promotion_refs != {digest_image_ref}:
        raise DeploymentRenderError("release environments do not promote the same digest")
    return digest_image_ref


def render_deployment(*, template: str, release_manifest: dict[str, Any]) -> str:
    if template.count(PLACEHOLDER_IMAGE_REF) != 1:
        raise DeploymentRenderError("deployment template must contain one target image placeholder")
    return template.replace(PLACEHOLDER_IMAGE_REF, release_image_ref(release_manifest))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-manifest", required=True, type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("deployment/kubernetes/base/portfolio-transaction-processing.yaml"),
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = cast(
        dict[str, Any],
        json.loads(args.release_manifest.read_text(encoding="utf-8")),
    )
    rendered = render_deployment(
        template=args.template.read_text(encoding="utf-8"),
        release_manifest=manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
