from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.release.image_release_evidence import (
    ImageReleaseEvidenceError,
    base_image_evidence_identity,
    provenance_verification_identity,
    sbom_identity,
    scan_receipt_identity,
    signature_verification_identity,
)

IMAGE_REF = "ghcr.io/sgajbi/lotus-core/query-service"
IMAGE_DIGEST = "sha256:" + "a" * 64
DOCKERFILE = "src/services/query_service/Dockerfile"
ISSUER = "https://token.actions.githubusercontent.com"
SUBJECT_PATTERN = r"repo:sgajbi/lotus-core:ref:refs/heads/main"
AUTHORITY = {
    "schema_version": "lotus-core.vulnerability-authority-bundle.v1",
    "bundle_sha256": "sha256:" + "f" * 64,
    "generated_at_utc": "2026-08-14T01:00:00Z",
    "repository": "sgajbi/lotus-core",
    "git_commit_sha": "1" * 40,
    "ci_run_id": "123",
    "ci_run_attempt": "1",
}
WORKFLOW_REF = (
    "https://github.com/sgajbi/lotus-core/.github/workflows/image-release.yml@refs/heads/main"
)
SBOM_SHA256 = "sha256:" + "9" * 64
PROVENANCE_KWARGS = {
    "repository": "sgajbi/lotus-core",
    "git_commit_sha": "1" * 40,
    "workflow_ref": WORKFLOW_REF,
    "service": "query_service",
    "dockerfile": DOCKERFILE,
    "ci_run_id": "123",
    "ci_run_attempt": "1",
    "sbom_sha256": SBOM_SHA256,
}


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _sbom(*, image_ref: str = IMAGE_REF, image_digest: str = IMAGE_DIGEST) -> dict[str, object]:
    encoded_digest = image_digest.replace(":", "%3A")
    encoded_ref = image_ref.replace("/", "%2F")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {
            "component": {
                "type": "container",
                "name": image_ref.rsplit("/", maxsplit=1)[-1],
                "purl": (f"pkg:oci/image@{encoded_digest}?arch=amd64&repository_url={encoded_ref}"),
            }
        },
        "components": [{"name": "runtime-package"}],
    }


def test_sbom_identity_requires_non_empty_cyclonedx(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "sbom.json",
        _sbom(),
    )

    identity = sbom_identity(path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST)

    assert identity["component_count"] == 1
    assert identity["subject"]["image_digest"] == IMAGE_DIGEST
    assert identity["subject"]["image_ref"] == IMAGE_REF
    assert identity["subject"]["purl"].startswith("pkg:oci/")
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


@pytest.mark.parametrize(
    ("image_ref", "image_digest"),
    [
        ("ghcr.io/sgajbi/lotus-core/other-service", IMAGE_DIGEST),
        (IMAGE_REF, "sha256:" + "b" * 64),
    ],
)
def test_sbom_identity_rejects_an_unrelated_declared_subject(
    tmp_path: Path, image_ref: str, image_digest: str
) -> None:
    with pytest.raises(ImageReleaseEvidenceError, match="subject drifted"):
        sbom_identity(
            _write(tmp_path / "sbom.json", _sbom(image_ref=image_ref, image_digest=image_digest)),
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
        )


def test_sbom_identity_rejects_missing_subject_metadata(tmp_path: Path) -> None:
    document = _sbom()
    document.pop("metadata")

    with pytest.raises(ImageReleaseEvidenceError, match="CycloneDX metadata"):
        sbom_identity(
            _write(tmp_path / "sbom.json", document),
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
        )


def _scan_receipt() -> dict[str, object]:
    return {
        "schema_version": "lotus-core.image-scan-policy-receipt.v6",
        "evidence_state": "available",
        "evidence_boundary": {"posture": "release", "release_eligible": True},
        "source": {
            "repository": "sgajbi/lotus-core",
            "git_commit_sha": "1" * 40,
            "ci_run_id": "123",
            "ci_run_attempt": "1",
        },
        "subject": {
            "service": "query_service",
            "image_ref": IMAGE_REF,
            "image_digest": IMAGE_DIGEST,
            "digest_image_ref": f"{IMAGE_REF}@{IMAGE_DIGEST}",
        },
        "scanner": {"name": "trivy", "report_sha256": "sha256:" + "2" * 64},
        "vulnerability_authority": AUTHORITY,
        "policy": {"policy_id": "policy", "decision": "passed", "finding_count": 0},
        "findings": [],
    }


def _scan_identity(path: Path) -> dict[str, object]:
    return scan_receipt_identity(
        path,
        service="query_service",
        image_ref=IMAGE_REF,
        image_digest=IMAGE_DIGEST,
        repository="sgajbi/lotus-core",
        git_commit_sha="1" * 40,
        ci_run_id="123",
        ci_run_attempt="1",
        vulnerability_authority=AUTHORITY,
    )


def test_scan_receipt_identity_requires_passed_release_evidence(tmp_path: Path) -> None:
    identity = _scan_identity(_write(tmp_path / "scan.json", _scan_receipt()))

    assert identity["policy"]["decision"] == "passed"
    assert identity["vulnerability_authority"] == AUTHORITY
    assert identity["subject"]["image_digest"] == IMAGE_DIGEST


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evidence_state", "unavailable", "unavailable"),
        ("evidence_boundary", {"posture": "diagnostic"}, "not release evidence"),
        ("policy", {"decision": "blocked"}, "did not pass"),
    ],
)
def test_scan_receipt_identity_rejects_non_release_posture(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    receipt = _scan_receipt()
    receipt[field] = value

    with pytest.raises(ImageReleaseEvidenceError, match=message):
        _scan_identity(_write(tmp_path / "scan.json", receipt))


def test_scan_receipt_identity_rejects_authority_substitution(tmp_path: Path) -> None:
    receipt = _scan_receipt()
    receipt["vulnerability_authority"] = {**AUTHORITY, "bundle_sha256": "sha256:" + "0" * 64}

    with pytest.raises(ImageReleaseEvidenceError, match="authority drifted"):
        _scan_identity(_write(tmp_path / "scan.json", receipt))


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

    identity = signature_verification_identity(
        path,
        image_ref=IMAGE_REF,
        image_digest=IMAGE_DIGEST,
        expected_issuer=ISSUER,
        expected_subject_pattern=SUBJECT_PATTERN,
    )

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
        signature_verification_identity(
            path,
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
            expected_issuer=ISSUER,
            expected_subject_pattern=SUBJECT_PATTERN,
        )


@pytest.mark.parametrize(
    ("issuer", "subject", "message"),
    [
        ("https://unexpected.example", "repo:sgajbi/lotus-core:ref:refs/heads/main", "issuer"),
        (ISSUER, "repo:attacker/fork:ref:refs/heads/main", "subject"),
    ],
)
def test_signature_identity_rejects_certificate_identity_drift(
    tmp_path: Path, issuer: str, subject: str, message: str
) -> None:
    path = _write(
        tmp_path / "signature.json",
        [
            {
                "critical": {
                    "image": {"docker-manifest-digest": IMAGE_DIGEST},
                    "identity": {"docker-reference": IMAGE_REF},
                },
                "optional": {"Issuer": issuer, "Subject": subject},
            }
        ],
    )

    with pytest.raises(ImageReleaseEvidenceError, match=message):
        signature_verification_identity(
            path,
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
            expected_issuer=ISSUER,
            expected_subject_pattern=SUBJECT_PATTERN,
        )


def _attestation_payload(digest: str = IMAGE_DIGEST) -> str:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": IMAGE_REF, "digest": {"sha256": digest.removeprefix("sha256:")}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/Attestations/GitHubActionsWorkflow@v1",
                "externalParameters": {
                    "repository": "sgajbi/lotus-core",
                    "workflow_ref": WORKFLOW_REF,
                    "service": "query_service",
                    "dockerfile": DOCKERFILE,
                },
                "internalParameters": {"ci_run_id": "123", "ci_run_attempt": "1"},
                "resolvedDependencies": [
                    {
                        "uri": "git+https://github.com/sgajbi/lotus-core",
                        "digest": {"gitCommit": "1" * 40},
                    }
                ],
            },
            "runDetails": {
                "builder": {"id": WORKFLOW_REF},
                "metadata": {"invocationId": "sgajbi/lotus-core/actions/runs/123/attempts/1"},
                "byproducts": [
                    {
                        "name": "buildx-result",
                        "content": base64.b64encode(
                            json.dumps({"containerimage.digest": digest}).encode()
                        ).decode(),
                    },
                    {"name": "cyclonedx-sbom", "digest": {"sha256": "9" * 64}},
                ],
            },
        },
    }
    return base64.b64encode(json.dumps(statement).encode()).decode()


def test_provenance_identity_decodes_and_binds_dsse_subject(tmp_path: Path) -> None:
    path = _write(tmp_path / "provenance.json", [{"payload": _attestation_payload()}])

    identity = provenance_verification_identity(
        path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST, **PROVENANCE_KWARGS
    )

    assert identity["predicate_types"] == ["https://slsa.dev/provenance/v1"]
    assert identity["subject"]["image_digest"] == IMAGE_DIGEST


def test_provenance_identity_rejects_subject_mismatch(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "provenance.json",
        [{"payload": _attestation_payload("sha256:" + "b" * 64)}],
    )
    with pytest.raises(ImageReleaseEvidenceError, match="subject digest drifted"):
        provenance_verification_identity(
            path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST, **PROVENANCE_KWARGS
        )


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
        provenance_verification_identity(
            path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST, **PROVENANCE_KWARGS
        )


def test_provenance_identity_rejects_legacy_slsa_v02_attestation(tmp_path: Path) -> None:
    statement = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "subject": [
            {"name": IMAGE_REF, "digest": {"sha256": IMAGE_DIGEST.removeprefix("sha256:")}}
        ],
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "predicate": {},
    }
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    path = _write(tmp_path / "provenance.json", [{"payload": payload}])

    with pytest.raises(ImageReleaseEvidenceError, match="statement type is invalid"):
        provenance_verification_identity(
            path, image_ref=IMAGE_REF, image_digest=IMAGE_DIGEST, **PROVENANCE_KWARGS
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"repository": "sgajbi/substituted"}, "external parameters"),
        ({"git_commit_sha": "2" * 40}, "source revision"),
        ({"workflow_ref": WORKFLOW_REF + "-other"}, "external parameters"),
        ({"service": "persistence_service"}, "external parameters"),
        ({"dockerfile": "src/services/persistence_service/Dockerfile"}, "external parameters"),
        ({"ci_run_id": "999"}, "run identity"),
        ({"ci_run_attempt": "2"}, "run identity"),
        ({"sbom_sha256": "sha256:" + "8" * 64}, "SBOM digest"),
    ],
)
def test_provenance_identity_rejects_source_and_evidence_substitution(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    path = _write(tmp_path / "provenance.json", [{"payload": _attestation_payload()}])

    with pytest.raises(ImageReleaseEvidenceError, match=message):
        provenance_verification_identity(
            path,
            image_ref=IMAGE_REF,
            image_digest=IMAGE_DIGEST,
            **{**PROVENANCE_KWARGS, **override},
        )


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
                    "observed_on": "2026-08-13",
                    "next_review_on": "2026-09-11",
                    "supported_through": "2027-06-30",
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
    dockerfile = tmp_path / DOCKERFILE
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_text(
        f"ARG PYTHON_IMAGE={base_image}\nFROM ${{PYTHON_IMAGE}} AS runtime-base\n",
        encoding="utf-8",
    )
    return inventory, manifest


def test_base_image_identity_binds_dockerfile_and_runtime_architecture(tmp_path: Path) -> None:
    inventory, manifest = _base_files(tmp_path)

    identity = base_image_evidence_identity(
        inventory_path=inventory,
        manifest_path=manifest,
        dockerfile_path=DOCKERFILE,
        verified_on=date(2026, 8, 14),
        repository_root=tmp_path,
    )

    assert identity["dockerfile"] == DOCKERFILE
    assert identity["deployment_platform"] == "linux/amd64"
    assert identity["runtime_manifest_digest"] == "sha256:" + "d" * 64
    assert identity["verified_on"] == "2026-08-14"
    assert identity["next_review_on"] == "2026-09-11"
    assert identity["declared_base_image"] == "python:3.11@sha256:" + "c" * 64
    assert identity["dockerfile_sha256"].startswith("sha256:")


def test_base_image_identity_rejects_architecture_drift(tmp_path: Path) -> None:
    inventory, manifest = _base_files(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["deployment_platform"] = "linux/arm64"
    _write(manifest, value)

    with pytest.raises(ImageReleaseEvidenceError, match="architecture drifted"):
        base_image_evidence_identity(
            inventory_path=inventory,
            manifest_path=manifest,
            dockerfile_path=DOCKERFILE,
            verified_on=date(2026, 8, 14),
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("observed_on", "2026-08-15", "future-dated"),
        ("next_review_on", "2026-08-13", "review is overdue"),
        ("supported_through", "2026-08-13", "support lifecycle has expired"),
        ("next_review_on", "not-a-date", "must be an ISO date"),
        ("supported_through", None, "must be an ISO date"),
    ],
)
def test_base_image_identity_revalidates_lifecycle_at_release_boundary(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    inventory, manifest = _base_files(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["base_images"][0][field] = value
    _write(inventory, payload)

    with pytest.raises(ImageReleaseEvidenceError, match=message):
        base_image_evidence_identity(
            inventory_path=inventory,
            manifest_path=manifest,
            dockerfile_path=DOCKERFILE,
            verified_on=date(2026, 8, 14),
            repository_root=tmp_path,
        )


def test_base_image_identity_rejects_dockerfile_base_drift(tmp_path: Path) -> None:
    inventory, manifest = _base_files(tmp_path)
    dockerfile = tmp_path / DOCKERFILE
    dockerfile.write_text(
        "ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:"
        + "f" * 64
        + "\nFROM ${PYTHON_IMAGE} AS runtime-base\n",
        encoding="utf-8",
    )

    with pytest.raises(ImageReleaseEvidenceError, match="base image drifted"):
        base_image_evidence_identity(
            inventory_path=inventory,
            manifest_path=manifest,
            dockerfile_path=DOCKERFILE,
            verified_on=date(2026, 8, 14),
            repository_root=tmp_path,
        )


@pytest.mark.parametrize(
    "dockerfile_content",
    [
        "FROM python:3.11-slim-bookworm AS runtime-base\n",
        "ARG PYTHON_IMAGE=python:3.11@sha256:" + "c" * 64 + "\n",
    ],
)
def test_base_image_identity_rejects_unbound_dockerfile_base(
    tmp_path: Path, dockerfile_content: str
) -> None:
    inventory, manifest = _base_files(tmp_path)
    (tmp_path / DOCKERFILE).write_text(dockerfile_content, encoding="utf-8")

    with pytest.raises(ImageReleaseEvidenceError, match="declare and consume"):
        base_image_evidence_identity(
            inventory_path=inventory,
            manifest_path=manifest,
            dockerfile_path=DOCKERFILE,
            verified_on=date(2026, 8, 14),
            repository_root=tmp_path,
        )
