from fastapi import FastAPI
from fastapi.testclient import TestClient

from portfolio_common.build_metadata import (
    BUILD_METADATA_RESPONSE_FIELDS,
    OCI_METADATA_LABELS,
    build_metadata_payload,
)
from portfolio_common.http_app_bootstrap import create_version_router


def test_build_metadata_payload_uses_unknown_for_missing_values(monkeypatch) -> None:
    for env_name in (
        "LOTUS_GIT_COMMIT_SHA",
        "LOTUS_GIT_BRANCH",
        "LOTUS_BUILD_TIMESTAMP",
        "LOTUS_REPO_URL",
        "LOTUS_IMAGE_VERSION",
        "LOTUS_IMAGE_DIGEST",
        "LOTUS_CI_RUN_ID",
    ):
        monkeypatch.delenv(env_name, raising=False)

    payload = build_metadata_payload(service_name="query_service")

    assert payload.service_name == "query_service"
    for field_name in BUILD_METADATA_RESPONSE_FIELDS:
        assert getattr(payload, field_name) == "unknown"
    assert payload.oci_labels == {label_name: "unknown" for label_name in OCI_METADATA_LABELS}


def test_version_endpoint_exposes_embedded_image_metadata(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_GIT_COMMIT_SHA", "abc123")
    monkeypatch.setenv("LOTUS_GIT_BRANCH", "feature/provenance")
    monkeypatch.setenv("LOTUS_BUILD_TIMESTAMP", "2026-07-05T12:34:56Z")
    monkeypatch.setenv("LOTUS_REPO_URL", "https://github.com/example/lotus-core")
    monkeypatch.setenv("LOTUS_IMAGE_VERSION", "abc123")
    monkeypatch.setenv("LOTUS_IMAGE_DIGEST", "sha256:123")
    monkeypatch.setenv("LOTUS_CI_RUN_ID", "987654")
    app = FastAPI()
    app.include_router(create_version_router(service_name="ingestion_service"))

    response = TestClient(app).get("/version")

    assert response.status_code == 200
    expected_metadata = {
        "service_name": "ingestion_service",
        "git_commit_sha": "abc123",
        "git_branch": "feature/provenance",
        "build_timestamp": "2026-07-05T12:34:56Z",
        "repo_url": "https://github.com/example/lotus-core",
        "image_version": "abc123",
        "image_digest": "sha256:123",
        "ci_pipeline_run_id": "987654",
    }
    expected_metadata["oci_labels"] = {
        "org.opencontainers.image.revision": "abc123",
        "org.opencontainers.image.ref.name": "feature/provenance",
        "org.opencontainers.image.created": "2026-07-05T12:34:56Z",
        "org.opencontainers.image.source": "https://github.com/example/lotus-core",
        "org.opencontainers.image.version": "abc123",
        "org.opencontainers.image.digest": "sha256:123",
        "org.opencontainers.image.ci.run_id": "987654",
    }
    assert response.json() == expected_metadata
