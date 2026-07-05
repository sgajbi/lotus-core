from scripts.write_image_release_manifest import SCHEMA_VERSION, build_release_manifest

FULL_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


def _build_manifest(**overrides):
    defaults = {
        "service": "query_service",
        "image_name": "query-service",
        "image_ref": "ghcr.io/sgajbi/lotus-core/query-service",
        "image_tag": f"ghcr.io/sgajbi/lotus-core/query-service:{FULL_SHA}",
        "image_digest": IMAGE_DIGEST,
        "git_commit_sha": FULL_SHA,
        "git_branch": "main",
        "image_version": FULL_SHA,
        "build_timestamp": "2026-07-05T12:34:56Z",
        "repo_url": "https://github.com/sgajbi/lotus-core",
        "ci_pipeline_run_id": "987654",
        "sbom_generated": True,
        "vulnerability_scan_status": "passed",
        "image_signed": True,
        "provenance_attestation_generated": True,
        "kubernetes_deploys_by_digest": True,
        "promotion_environments": ["dev", "uat", "prod"],
    }
    defaults.update(overrides)
    return build_release_manifest(**defaults)


def test_image_release_manifest_records_digest_promotion_and_runtime_metadata() -> None:
    manifest = _build_manifest()

    digest_ref = "ghcr.io/sgajbi/lotus-core/query-service@" + IMAGE_DIGEST
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["digest_image_ref"] == digest_ref
    assert manifest["same_image_promoted_across_environments"] is True
    assert manifest["kubernetes_deploys_by_digest"] is True
    assert manifest["runtime_env"] == {
        "LOTUS_GIT_COMMIT_SHA": FULL_SHA,
        "LOTUS_GIT_BRANCH": "main",
        "LOTUS_BUILD_TIMESTAMP": "2026-07-05T12:34:56Z",
        "LOTUS_REPO_URL": "https://github.com/sgajbi/lotus-core",
        "LOTUS_IMAGE_VERSION": FULL_SHA,
        "LOTUS_CI_RUN_ID": "987654",
    }
    assert manifest["oci_labels"] == {
        "org.opencontainers.image.revision": FULL_SHA,
        "org.opencontainers.image.ref.name": "main",
        "org.opencontainers.image.created": "2026-07-05T12:34:56Z",
        "org.opencontainers.image.source": "https://github.com/sgajbi/lotus-core",
        "org.opencontainers.image.version": FULL_SHA,
        "org.opencontainers.image.ci.run_id": "987654",
    }
    assert manifest["image_digest"] == IMAGE_DIGEST
    assert [promotion["image_ref"] for promotion in manifest["promotions"]] == [
        digest_ref,
        digest_ref,
        digest_ref,
    ]


def test_image_release_manifest_rejects_non_git_sha_tag() -> None:
    try:
        _build_manifest(image_tag="ghcr.io/sgajbi/lotus-core/query-service:latest")
    except SystemExit as exc:
        assert "image tag must be the Git commit SHA tag" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected manifest writer to reject non-SHA image tag")


def test_image_release_manifest_rejects_short_git_sha() -> None:
    try:
        _build_manifest(
            image_tag="ghcr.io/sgajbi/lotus-core/query-service:abc123",
            git_commit_sha="abc123",
            image_version="abc123",
        )
    except SystemExit as exc:
        assert "full 40-character lowercase hexadecimal SHA" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected manifest writer to reject short Git SHA metadata")


def test_image_release_manifest_rejects_failed_scan() -> None:
    try:
        _build_manifest(vulnerability_scan_status="failed")
    except SystemExit as exc:
        assert "vulnerability scan status must be passed" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected manifest writer to reject failed vulnerability scan")


def test_image_release_manifest_rejects_missing_supply_chain_evidence() -> None:
    for field_name in (
        "sbom_generated",
        "image_signed",
        "provenance_attestation_generated",
        "kubernetes_deploys_by_digest",
    ):
        try:
            _build_manifest(**{field_name: False})
        except SystemExit:
            continue
        raise AssertionError(f"expected manifest writer to reject {field_name}=False")


def test_image_release_manifest_rejects_partial_promotion_path() -> None:
    try:
        _build_manifest(promotion_environments=["dev"])
    except SystemExit as exc:
        assert "promotion environments must include dev, uat, prod" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected manifest writer to reject partial promotion environments")


def test_image_release_manifest_rejects_unknown_release_identity() -> None:
    try:
        _build_manifest(repo_url="unknown")
    except SystemExit as exc:
        assert "repo URL is required" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected manifest writer to reject unknown repo URL")
