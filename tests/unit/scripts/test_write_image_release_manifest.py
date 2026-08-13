import pytest

from scripts.release.write_image_release_manifest import SCHEMA_VERSION, build_release_manifest

FULL_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE_REF = "ghcr.io/sgajbi/lotus-core/query-service"


def _evidence(*, digest: str = IMAGE_DIGEST) -> dict[str, object]:
    subject = {"image_ref": IMAGE_REF, "image_digest": digest}
    source = {
        "repository": "sgajbi/lotus-core",
        "git_commit_sha": FULL_SHA,
        "ci_run_id": "987654",
        "ci_run_attempt": "1",
    }
    scan_subject = {
        "service": "query_service",
        **subject,
        "digest_image_ref": f"{IMAGE_REF}@{digest}",
    }
    return {
        "scan_receipt": {
            "subject": scan_subject,
            "source": source,
            "policy": {"decision": "passed"},
            "sha256": "sha256:" + "1" * 64,
        },
        "sbom": {"subject": subject, "sha256": "sha256:" + "2" * 64},
        "signature_verification": {
            "subject": subject,
            "sha256": "sha256:" + "3" * 64,
        },
        "provenance_verification": {
            "subject": subject,
            "sha256": "sha256:" + "4" * 64,
        },
        "base_image": {
            "dockerfile": "src/services/query_service/Dockerfile",
            "runtime_manifest_digest": "sha256:" + "5" * 64,
        },
    }


def _promotion_receipts() -> list[dict[str, str]]:
    digest_ref = f"{IMAGE_REF}@{IMAGE_DIGEST}"
    return [
        {
            "environment": environment,
            "image_ref": digest_ref,
            "receipt_sha256": "sha256:" + str(index) * 64,
        }
        for index, environment in enumerate(("dev", "uat", "prod"), start=6)
    ]


def _build_manifest(**overrides):
    defaults = {
        "service": "query_service",
        "image_name": "query-service",
        "image_ref": IMAGE_REF,
        "image_tag": f"{IMAGE_REF}:{FULL_SHA}",
        "image_digest": IMAGE_DIGEST,
        "git_commit_sha": FULL_SHA,
        "git_branch": "main",
        "image_version": FULL_SHA,
        "build_timestamp": "2026-07-05T12:34:56Z",
        "repo_url": "https://github.com/sgajbi/lotus-core",
        "repository": "sgajbi/lotus-core",
        "ci_pipeline_run_id": "987654",
        "ci_run_attempt": "1",
        **_evidence(),
        "promotion_receipts": _promotion_receipts(),
    }
    defaults.update(overrides)
    return build_release_manifest(**defaults)


def test_image_release_manifest_records_verified_evidence_and_promotions() -> None:
    manifest = _build_manifest()

    digest_ref = f"{IMAGE_REF}@{IMAGE_DIGEST}"
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["release_posture"] == "promoted"
    assert manifest["digest_image_ref"] == digest_ref
    assert manifest["same_image_promoted_across_environments"] is True
    assert manifest["kubernetes_deploys_by_digest"] is True
    assert manifest["evidence"]["vulnerability_scan"]["sha256"] == "sha256:" + "1" * 64
    assert manifest["runtime_env"]["LOTUS_GIT_COMMIT_SHA"] == FULL_SHA
    assert manifest["oci_labels"]["org.opencontainers.image.revision"] == FULL_SHA
    assert [promotion["image_ref"] for promotion in manifest["promotions"]] == [
        digest_ref,
        digest_ref,
        digest_ref,
    ]


def test_image_release_manifest_is_truthful_without_promotion_receipts() -> None:
    manifest = _build_manifest(promotion_receipts=[])

    assert manifest["release_posture"] == "candidate"
    assert manifest["promotion_eligible"] is True
    assert manifest["same_image_promoted_across_environments"] is False
    assert manifest["kubernetes_deploys_by_digest"] is False
    assert manifest["promotions"] == []


def test_image_release_manifest_rejects_non_git_sha_tag() -> None:
    with pytest.raises(SystemExit, match="image tag must be the Git commit SHA tag"):
        _build_manifest(image_tag=f"{IMAGE_REF}:latest")


def test_image_release_manifest_rejects_short_git_sha() -> None:
    with pytest.raises(SystemExit, match="full 40-character lowercase hexadecimal SHA"):
        _build_manifest(
            image_tag=f"{IMAGE_REF}:abc123",
            git_commit_sha="abc123",
            image_version="abc123",
        )


def test_image_release_manifest_rejects_failed_scan() -> None:
    evidence = _evidence()
    evidence["scan_receipt"]["policy"] = {"decision": "blocked"}
    with pytest.raises(SystemExit, match="passed decision"):
        _build_manifest(**evidence)


@pytest.mark.parametrize(
    "field_name",
    ["scan_receipt", "sbom", "signature_verification", "provenance_verification"],
)
def test_image_release_manifest_rejects_subject_drift(field_name: str) -> None:
    evidence = _evidence()
    evidence[field_name]["subject"] = {
        "image_ref": IMAGE_REF,
        "image_digest": "sha256:" + "c" * 64,
    }
    with pytest.raises(SystemExit, match="release subject"):
        _build_manifest(**evidence)


def test_image_release_manifest_rejects_unverified_promotion() -> None:
    receipt = _promotion_receipts()[0]
    receipt["image_ref"] = f"{IMAGE_REF}@sha256:" + "c" * 64
    with pytest.raises(SystemExit, match="does not bind the release digest"):
        _build_manifest(promotion_receipts=[receipt])


def test_image_release_manifest_rejects_unknown_release_identity() -> None:
    with pytest.raises(SystemExit, match="repo URL is required"):
        _build_manifest(repo_url="unknown")
