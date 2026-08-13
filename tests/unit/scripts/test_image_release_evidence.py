from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.release.image_release_evidence import (
    ImageReleaseEvidenceError,
    base_image_evidence_identity,
    provenance_verification_identity,
    sbom_identity,
    signature_verification_identity,
)

IMAGE_REF = "ghcr.io/sgajbi/lotus-core/query-service"
IMAGE_DIGEST = "sha256:" + "a" * 64
DOCKERFILE = "src/services/query_service/Dockerfile"


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_sbom_identity_requires_non_empty_cyclonedx(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "sbom.json",
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [{"name": "x"}]},
    )

    identity = sbom_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)

    assert identity["component_count"] == 1
    assert identity["subject"]["image_digest"] == IMAGE_DIGEST
    assert identity["sha256"].startswith("sha256:")


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"bomFormat": "SPDX", "specVersion": "1", "components": [{}]},
        {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []},
    ],
)
def test_sbom_identity_rejects_malformed_or_empty_documents(
    tmp_path: Path, document: dict[str, object]
) -> None:
    with pytest.raises(ImageReleaseEvidenceError):
        sbom_identity(
            _write(tmp_path / "sbom.json", document),
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
        )


def test_signature_identity_requires_exact_digest_ref_and_certificate(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "signature.json",
        [
            {
                "critical": {
                    "image": {"docker-manifest-digest": IMAGE_DIGEST},
                    "identity": {"docker-reference": IMAGE_REF},
                },
                "optional": {
                    "Issuer": "https://token.actions.githubusercontent.com",
                    "Subject": "repo:sgajbi/lotus-core:ref:refs/heads/main",
                },
            }
        ],
    )

    identity = signature_verification_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)

    assert identity["verification_count"] == 1
    assert identity["certificate_identities"][0]["subject"].startswith("repo:sgajbi/")


def test_signature_identity_rejects_artifact_mismatch(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "signature.json",
        [
            {
                "critical": {
                    "image": {"docker-manifest-digest": "sha256:" + "b" * 64},
                    "identity": {"docker-reference": IMAGE_REF},
                },
                "optional": {"Issuer": "issuer", "Subject": "subject"},
            }
        ],
    )
    with pytest.raises(ImageReleaseEvidenceError, match="digest drifted"):
        signature_verification_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)


def _attestation_payload(digest: str = IMAGE_DIGEST) -> str:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": IMAGE_REF, "digest": {"sha256": digest.removeprefix("sha256:")}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {"buildDefinition": {}},
    }
    return base64.b64encode(json.dumps(statement).encode()).decode()


def test_provenance_identity_decodes_and_binds_dsse_subject(tmp_path: Path) -> None:
    path = _write(tmp_path / "provenance.json", [{"payload": _attestation_payload()}])

    identity = provenance_verification_identity(
        path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST
    )

    assert identity["predicate_types"] == ["https://slsa.dev/provenance/v1"]
    assert identity["subject"]["image_digest"] == IMAGE_DIGEST


def test_provenance_identity_rejects_subject_mismatch(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "provenance.json",
        [{"payload": _attestation_payload("sha256:" + "b" * 64)}],
    )
    with pytest.raises(ImageReleaseEvidenceError, match="subject digest drifted"):
        provenance_verification_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)


def test_provenance_identity_rejects_non_slsa_attestation(tmp_path: Path) -> None:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": IMAGE_REF, "digest": {"sha256": IMAGE_DIGEST.removeprefix("sha256:")}}
        ],
        "predicateType": "https://example.com/custom-attestation/v1",
        "predicate": {},
    }
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    path = _write(tmp_path / "provenance.json", [{"payload": payload}])

    with pytest.raises(ImageReleaseEvidenceError, match="must be SLSA provenance"):
        provenance_verification_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)


def _base_files(tmp_path: Path) -> tuple[Path, Path]:
    base_image = "python:3.11@sha256:" + "c" * 64
    runtime_digest = "sha256:" + "d" * 64
    config_digest = "sha256:" + "e" * 64
    inventory = _write(
        tmp_path / "inventory.json",
        {
            "schema_version": "lotus-core.base-image-lifecycle-inventory.v1",
            "base_images": [
                {
                    "image": base_image,
                    "deployment_platform": "linux/amd64",
                    "resolved_manifest_digest": runtime_digest,
                    "config_digest": config_digest,
                    "covered_dockerfiles": [DOCKERFILE],
                }
            ],
        },
    )
    manifest = _write(
        tmp_path / "manifest.json",
        {
            "schema_version": "lotus-core.base-image-manifest-evidence.v1",
            "image": base_image,
            "deployment_platform": "linux/amd64",
            "runtime_manifest": {"digest": runtime_digest, "config_digest": config_digest},
        },
    )
    return inventory, manifest


def test_base_image_identity_binds_dockerfile_and_runtime_architecture(tmp_path: Path) -> None:
    inventory, manifest = _base_files(tmp_path)

    identity = base_image_evidence_identity(
        inventory_path=inventory, manifest_path=manifest, dockerfile_path=DOCKERFILE
    )

    assert identity["dockerfile"] == DOCKERFILE
    assert identity["deployment_platform"] == "linux/amd64"
    assert identity["runtime_manifest_digest"] == "sha256:" + "d" * 64


def test_base_image_identity_rejects_architecture_drift(tmp_path: Path) -> None:
    inventory, manifest = _base_files(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["deployment_platform"] = "linux/arm64"
    _write(manifest, value)

    with pytest.raises(ImageReleaseEvidenceError, match="architecture drifted"):
        base_image_evidence_identity(
            inventory_path=inventory, manifest_path=manifest, dockerfile_path=DOCKERFILE
        )
