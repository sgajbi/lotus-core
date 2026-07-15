"""Render digest-pinned Kubernetes deployments from governed image evidence."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)
DIGEST_IMAGE_PATTERN = re.compile(r"^ghcr\.io/sgajbi/lotus-core/.+@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentTarget:
    """Identify one release image and its immutable deployment template."""

    service: str
    image_name: str
    template: Path

    @property
    def placeholder_image_ref(self) -> str:
        """Return the all-zero digest reference expected in source control."""

        return f"ghcr.io/sgajbi/lotus-core/{self.image_name}@{PLACEHOLDER_DIGEST}"


DEPLOYMENT_TARGETS = {
    target.service: target
    for target in (
        DeploymentTarget(
            service="portfolio_transaction_processing_service",
            image_name="portfolio-transaction-processing-service",
            template=Path("deployment/kubernetes/base/portfolio-transaction-processing.yaml"),
        ),
        DeploymentTarget(
            service="portfolio_derived_state_service",
            image_name="portfolio-derived-state-service",
            template=Path("deployment/kubernetes/base/portfolio-derived-state.yaml"),
        ),
    )
}


class DeploymentRenderError(ValueError):
    """Raised when release evidence cannot authorize an immutable deployment."""


def release_image_ref(
    manifest: dict[str, Any],
    *,
    target: DeploymentTarget,
) -> str:
    """Validate release evidence and return its immutable image reference."""

    if manifest.get("service") != target.service:
        raise DeploymentRenderError("release manifest does not belong to the target service")
    if manifest.get("image_name") != target.image_name:
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
    if not digest_image_ref.startswith(f"ghcr.io/sgajbi/lotus-core/{target.image_name}@"):
        raise DeploymentRenderError("release digest belongs to an unexpected image")
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


def render_deployment(
    *,
    template: str,
    release_manifest: dict[str, Any],
    target: DeploymentTarget,
) -> str:
    """Replace one governed placeholder with an authorized digest reference."""

    if template.count(target.placeholder_image_ref) != 1:
        raise DeploymentRenderError("deployment template must contain one target image placeholder")
    return template.replace(
        target.placeholder_image_ref,
        release_image_ref(release_manifest, target=target),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=sorted(DEPLOYMENT_TARGETS))
    parser.add_argument("--release-manifest", required=True, type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Render one configured deployment target from its release manifest."""

    args = _parse_args()
    target = DEPLOYMENT_TARGETS[args.service]
    template = args.template or target.template
    manifest = cast(
        dict[str, Any],
        json.loads(args.release_manifest.read_text(encoding="utf-8")),
    )
    rendered = render_deployment(
        template=template.read_text(encoding="utf-8"),
        release_manifest=manifest,
        target=target,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
