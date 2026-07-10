import copy

import pytest

from scripts.render_transaction_processing_deployment import (
    PLACEHOLDER_IMAGE_REF,
    DeploymentRenderError,
    render_deployment,
)

DIGEST = "sha256:" + ("a" * 64)
DIGEST_IMAGE_REF = "ghcr.io/sgajbi/lotus-core/portfolio-transaction-processing-service@" + DIGEST


def _manifest() -> dict[str, object]:
    return {
        "service": "portfolio_transaction_processing_service",
        "image_name": "portfolio-transaction-processing-service",
        "image_digest": DIGEST,
        "digest_image_ref": DIGEST_IMAGE_REF,
        "sbom_generated": True,
        "vulnerability_scan_status": "passed",
        "image_signed": True,
        "provenance_attestation_generated": True,
        "kubernetes_deploys_by_digest": True,
        "same_image_promoted_across_environments": True,
        "promotions": [
            {"environment": environment, "image_ref": DIGEST_IMAGE_REF}
            for environment in ("dev", "uat", "prod")
        ],
    }


def test_render_deployment_uses_the_same_release_digest() -> None:
    rendered = render_deployment(
        template=f"image: {PLACEHOLDER_IMAGE_REF}\n",
        release_manifest=_manifest(),
    )

    assert rendered == f"image: {DIGEST_IMAGE_REF}\n"


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
def test_render_deployment_rejects_untrusted_release_evidence(field: str, value: object) -> None:
    manifest = _manifest()
    manifest[field] = value

    with pytest.raises(DeploymentRenderError):
        render_deployment(
            template=f"image: {PLACEHOLDER_IMAGE_REF}\n",
            release_manifest=manifest,
        )


def test_render_deployment_rejects_cross_environment_digest_drift() -> None:
    manifest = copy.deepcopy(_manifest())
    promotions = manifest["promotions"]
    assert isinstance(promotions, list)
    promotions[-1]["image_ref"] = "ghcr.io/sgajbi/lotus-core/target@sha256:" + ("b" * 64)

    with pytest.raises(DeploymentRenderError, match="same digest"):
        render_deployment(
            template=f"image: {PLACEHOLDER_IMAGE_REF}\n",
            release_manifest=manifest,
        )


def test_render_deployment_rejects_missing_or_duplicate_placeholder() -> None:
    for template in ("kind: Deployment\n", PLACEHOLDER_IMAGE_REF * 2):
        with pytest.raises(DeploymentRenderError, match="one target image placeholder"):
            render_deployment(template=template, release_manifest=_manifest())
