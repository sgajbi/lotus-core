"""Prove immutable deployment rendering for release-managed Core services."""

import copy

import pytest

from scripts.release.render_release_deployment import (
    DEPLOYMENT_TARGETS,
    DeploymentRenderError,
    DeploymentTarget,
    render_deployment,
)

DIGEST = "sha256:" + ("a" * 64)


def _manifest(target: DeploymentTarget) -> dict[str, object]:
    digest_image_ref = f"ghcr.io/sgajbi/lotus-core/{target.image_name}@{DIGEST}"
    return {
        "service": target.service,
        "image_name": target.image_name,
        "image_digest": DIGEST,
        "digest_image_ref": digest_image_ref,
        "sbom_generated": True,
        "vulnerability_scan_status": "passed",
        "image_signed": True,
        "provenance_attestation_generated": True,
        "kubernetes_deploys_by_digest": True,
        "same_image_promoted_across_environments": True,
        "promotions": [
            {"environment": environment, "image_ref": digest_image_ref}
            for environment in ("dev", "uat", "prod")
        ],
    }


@pytest.mark.parametrize("target", DEPLOYMENT_TARGETS.values(), ids=lambda item: item.service)
def test_render_deployment_uses_the_same_release_digest(target: DeploymentTarget) -> None:
    manifest = _manifest(target)

    rendered = render_deployment(
        template=f"image: {target.placeholder_image_ref}\n",
        release_manifest=manifest,
        target=target,
    )

    assert rendered == f"image: {manifest['digest_image_ref']}\n"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("service", "cost_calculator_service"),
        ("sbom_generated", False),
        ("vulnerability_scan_status", "failed"),
        ("image_signed", False),
        ("provenance_attestation_generated", False),
        ("kubernetes_deploys_by_digest", False),
        ("same_image_promoted_across_environments", False),
    ],
)
def test_render_deployment_rejects_untrusted_release_evidence(
    field: str,
    value: object,
) -> None:
    target = DEPLOYMENT_TARGETS["portfolio_derived_state_service"]
    manifest = _manifest(target)
    manifest[field] = value

    with pytest.raises(DeploymentRenderError):
        render_deployment(
            template=f"image: {target.placeholder_image_ref}\n",
            release_manifest=manifest,
            target=target,
        )


def test_render_deployment_rejects_cross_environment_digest_drift() -> None:
    target = DEPLOYMENT_TARGETS["portfolio_derived_state_service"]
    manifest = copy.deepcopy(_manifest(target))
    promotions = manifest["promotions"]
    assert isinstance(promotions, list)
    promotions[-1]["image_ref"] = "ghcr.io/sgajbi/lotus-core/target@sha256:" + ("b" * 64)

    with pytest.raises(DeploymentRenderError, match="same digest"):
        render_deployment(
            template=f"image: {target.placeholder_image_ref}\n",
            release_manifest=manifest,
            target=target,
        )


def test_render_deployment_rejects_missing_or_duplicate_placeholder() -> None:
    target = DEPLOYMENT_TARGETS["portfolio_derived_state_service"]
    for template in ("kind: Deployment\n", target.placeholder_image_ref * 2):
        with pytest.raises(DeploymentRenderError, match="one target image placeholder"):
            render_deployment(
                template=template,
                release_manifest=_manifest(target),
                target=target,
            )
