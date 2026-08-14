"""Validate same-artifact image evidence before release-manifest construction."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SCHEMA_VERSION = "lotus-core.image-release-evidence.v1"
SLSA_PROVENANCE_PREDICATE_TYPES = {"https://slsa.dev/provenance/v1"}
SCAN_RECEIPT_SCHEMA_VERSION = "lotus-core.image-scan-policy-receipt.v6"


class ImageReleaseEvidenceError(ValueError):
    """Raised when release evidence is missing, malformed, or artifact-mismatched."""


def _json(path: Path, *, name: str) -> tuple[bytes, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImageReleaseEvidenceError(f"cannot read {name}") from exc
    return content, value


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _iso_date(value: object, *, field: str) -> date:
    if not isinstance(value, str):
        raise ImageReleaseEvidenceError(f"base lifecycle {field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ImageReleaseEvidenceError(f"base lifecycle {field} must be an ISO date") from exc


def _object(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ImageReleaseEvidenceError(f"{name} must be an object")
    return value


def _array(value: Any, *, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ImageReleaseEvidenceError(f"{name} must be a non-empty array")
    return value


def _validate_subject(*, image_ref: str, image_digest: str) -> None:
    if not image_ref.strip():
        raise ImageReleaseEvidenceError("image ref is required")
    if not SHA256_PATTERN.fullmatch(image_digest):
        raise ImageReleaseEvidenceError("image digest must be a sha256 digest")


def _cyclonedx_image_subject(
    sbom: dict[str, Any], *, image_ref: str, image_digest: str
) -> dict[str, str]:
    """Read the OCI subject declared by Trivy's CycloneDX metadata component."""
    metadata = _object(sbom.get("metadata"), name="CycloneDX metadata")
    component = _object(metadata.get("component"), name="CycloneDX metadata component")
    if component.get("type") != "container":
        raise ImageReleaseEvidenceError("SBOM metadata subject must be a container")
    purl = component.get("purl")
    if not isinstance(purl, str) or not purl.startswith("pkg:oci/"):
        raise ImageReleaseEvidenceError("SBOM metadata subject must have an OCI purl")
    coordinates, separator, query = purl.removeprefix("pkg:oci/").partition("?")
    name, digest_separator, encoded_digest = coordinates.rpartition("@")
    if not separator or not digest_separator or not name:
        raise ImageReleaseEvidenceError("SBOM metadata OCI purl is malformed")
    parameters = parse_qs(query, keep_blank_values=True)
    repositories = parameters.get("repository_url", [])
    if len(repositories) != 1:
        raise ImageReleaseEvidenceError("SBOM metadata OCI repository is required")
    declared_ref = repositories[0]
    declared_digest = unquote(encoded_digest)
    if declared_ref != image_ref or declared_digest != image_digest:
        raise ImageReleaseEvidenceError("SBOM metadata image subject drifted")
    return {"image_ref": declared_ref, "image_digest": declared_digest, "purl": purl}


def sbom_identity(path: Path, *, image_ref: str, image_digest: str) -> dict[str, Any]:
    """Validate CycloneDX bytes and their declared OCI subject identity."""
    _validate_subject(image_ref=image_ref, image_digest=image_digest)
    content, raw = _json(path, name="CycloneDX SBOM")
    sbom = _object(raw, name="CycloneDX SBOM")
    if sbom.get("bomFormat") != "CycloneDX":
        raise ImageReleaseEvidenceError("SBOM must use CycloneDX")
    spec_version = sbom.get("specVersion")
    if not isinstance(spec_version, str) or not spec_version.strip():
        raise ImageReleaseEvidenceError("SBOM spec version is required")
    components = sbom.get("components")
    if not isinstance(components, list) or not components:
        raise ImageReleaseEvidenceError("SBOM must contain components")
    subject = _cyclonedx_image_subject(sbom, image_ref=image_ref, image_digest=image_digest)
    return {
        "media_type": "application/vnd.cyclonedx+json",
        "sha256": _sha256(content),
        "bom_format": "CycloneDX",
        "spec_version": spec_version,
        "component_count": len(components),
        "subject": subject,
    }


def scan_receipt_identity(
    path: Path,
    *,
    service: str,
    image_ref: str,
    image_digest: str,
    repository: str,
    git_commit_sha: str,
    ci_run_id: str,
    ci_run_attempt: str,
    vulnerability_authority: dict[str, str],
) -> dict[str, Any]:
    """Validate a passed release scan receipt and bind its immutable identities."""
    _validate_subject(image_ref=image_ref, image_digest=image_digest)
    content, raw = _json(path, name="image scan policy receipt")
    receipt = _object(raw, name="image scan policy receipt")
    if receipt.get("schema_version") != SCAN_RECEIPT_SCHEMA_VERSION:
        raise ImageReleaseEvidenceError("image scan receipt version is invalid")
    if receipt.get("evidence_state") != "available":
        raise ImageReleaseEvidenceError("image scan evidence is unavailable")
    expected_source = {
        "repository": repository,
        "git_commit_sha": git_commit_sha,
        "ci_run_id": ci_run_id,
        "ci_run_attempt": ci_run_attempt,
    }
    if receipt.get("source") != expected_source:
        raise ImageReleaseEvidenceError("image scan source identity drifted")
    expected_subject = {
        "service": service,
        "image_ref": image_ref,
        "image_digest": image_digest,
        "digest_image_ref": f"{image_ref}@{image_digest}",
    }
    if receipt.get("subject") != expected_subject:
        raise ImageReleaseEvidenceError("image scan subject identity drifted")
    if receipt.get("vulnerability_authority") != vulnerability_authority:
        raise ImageReleaseEvidenceError("image scan vulnerability authority drifted")
    boundary = receipt.get("evidence_boundary")
    if not isinstance(boundary, dict) or boundary.get("posture") != "release":
        raise ImageReleaseEvidenceError("image scan receipt is not release evidence")
    if boundary.get("release_eligible") is not True:
        raise ImageReleaseEvidenceError("image scan receipt is not release eligible")
    policy = receipt.get("policy")
    if not isinstance(policy, dict) or policy.get("decision") != "passed":
        raise ImageReleaseEvidenceError("image scan policy did not pass")
    return {
        "schema_version": SCAN_RECEIPT_SCHEMA_VERSION,
        "sha256": _sha256(content),
        "scanner": receipt.get("scanner"),
        "policy": policy,
        "vulnerability_authority": vulnerability_authority,
        "subject": expected_subject,
        "source": expected_source,
    }


def signature_verification_identity(
    path: Path,
    *,
    image_ref: str,
    image_digest: str,
    expected_issuer: str,
    expected_subject_pattern: str,
) -> dict[str, Any]:
    """Validate Cosign verification output for exactly the target digest."""
    _validate_subject(image_ref=image_ref, image_digest=image_digest)
    content, raw = _json(path, name="Cosign signature verification")
    entries = _array(raw, name="Cosign signature verification")
    try:
        subject_pattern = re.compile(expected_subject_pattern)
    except re.error as exc:
        raise ImageReleaseEvidenceError("signature subject pattern is invalid") from exc
    identities: list[dict[str, str]] = []
    for entry in entries:
        item = _object(entry, name="Cosign signature entry")
        critical = _object(item.get("critical"), name="Cosign critical identity")
        image = _object(critical.get("image"), name="Cosign image identity")
        identity = _object(critical.get("identity"), name="Cosign repository identity")
        if image.get("docker-manifest-digest") != image_digest:
            raise ImageReleaseEvidenceError("signature verification image digest drifted")
        if identity.get("docker-reference") != image_ref:
            raise ImageReleaseEvidenceError("signature verification image ref drifted")
        optional = _object(item.get("optional"), name="Cosign optional claims")
        issuer = optional.get("Issuer") or optional.get("issuer")
        subject = optional.get("Subject") or optional.get("subject")
        if not isinstance(issuer, str) or not issuer.strip():
            raise ImageReleaseEvidenceError("signature verification issuer is required")
        if not isinstance(subject, str) or not subject.strip():
            raise ImageReleaseEvidenceError("signature verification subject is required")
        if issuer != expected_issuer:
            raise ImageReleaseEvidenceError("signature verification issuer drifted")
        if subject_pattern.fullmatch(subject) is None:
            raise ImageReleaseEvidenceError("signature verification subject drifted")
        identities.append({"issuer": issuer, "subject": subject})
    return {
        "media_type": "application/vnd.dev.cosign.simplesigning.v1+json",
        "sha256": _sha256(content),
        "verification_count": len(entries),
        "certificate_identities": identities,
        "expected_certificate_issuer": expected_issuer,
        "expected_certificate_subject_pattern": expected_subject_pattern,
        "subject": {"image_ref": image_ref, "image_digest": image_digest},
    }


def provenance_verification_identity(
    path: Path,
    *,
    image_ref: str,
    image_digest: str,
    repository: str,
    git_commit_sha: str,
    workflow_ref: str,
    service: str,
    dockerfile: str,
    ci_run_id: str,
    ci_run_attempt: str,
    sbom_sha256: str,
) -> dict[str, Any]:
    """Validate signed DSSE provenance subjects against the exact image digest."""
    _validate_subject(image_ref=image_ref, image_digest=image_digest)
    content, raw = _json(path, name="Cosign provenance verification")
    entries = _array(raw, name="Cosign provenance verification")
    predicate_types: set[str] = set()
    digest_hex = image_digest.removeprefix("sha256:")
    for entry in entries:
        envelope = _object(entry, name="Cosign provenance envelope")
        payload = envelope.get("payload")
        if not isinstance(payload, str) or not payload:
            raise ImageReleaseEvidenceError("provenance envelope payload is required")
        try:
            statement = json.loads(base64.b64decode(payload, validate=True))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ImageReleaseEvidenceError("provenance payload is invalid") from exc
        statement = _object(statement, name="provenance statement")
        if statement.get("_type") != "https://in-toto.io/Statement/v1":
            raise ImageReleaseEvidenceError("provenance statement type is invalid")
        predicate_type = statement.get("predicateType")
        if predicate_type not in SLSA_PROVENANCE_PREDICATE_TYPES:
            raise ImageReleaseEvidenceError("provenance predicate type must be SLSA provenance")
        subjects = statement.get("subject")
        if not isinstance(subjects, list) or not any(
            isinstance(subject, dict)
            and subject.get("name") == image_ref
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256") == digest_hex
            for subject in subjects
        ):
            raise ImageReleaseEvidenceError("provenance subject digest drifted")
        predicate = _object(statement.get("predicate"), name="provenance predicate")
        build_definition = _object(
            predicate.get("buildDefinition"), name="provenance build definition"
        )
        if build_definition.get("buildType") != (
            "https://github.com/Attestations/GitHubActionsWorkflow@v1"
        ):
            raise ImageReleaseEvidenceError("provenance build type drifted")
        if build_definition.get("externalParameters") != {
            "repository": repository,
            "workflow_ref": workflow_ref,
            "service": service,
            "dockerfile": dockerfile,
        }:
            raise ImageReleaseEvidenceError("provenance external parameters drifted")
        if build_definition.get("internalParameters") != {
            "ci_run_id": ci_run_id,
            "ci_run_attempt": ci_run_attempt,
        }:
            raise ImageReleaseEvidenceError("provenance run identity drifted")
        dependencies = build_definition.get("resolvedDependencies")
        expected_dependency = {
            "uri": f"git+https://github.com/{repository}",
            "digest": {"gitCommit": git_commit_sha},
        }
        if dependencies != [expected_dependency]:
            raise ImageReleaseEvidenceError("provenance source revision drifted")
        run_details = _object(predicate.get("runDetails"), name="provenance run details")
        if run_details.get("builder") != {"id": workflow_ref}:
            raise ImageReleaseEvidenceError("provenance builder identity drifted")
        expected_invocation = f"{repository}/actions/runs/{ci_run_id}/attempts/{ci_run_attempt}"
        metadata = _object(run_details.get("metadata"), name="provenance run metadata")
        if metadata.get("invocationId") != expected_invocation:
            raise ImageReleaseEvidenceError("provenance invocation identity drifted")
        byproducts = run_details.get("byproducts")
        if not isinstance(byproducts, list):
            raise ImageReleaseEvidenceError("provenance byproducts are missing")
        buildx = next(
            (
                item
                for item in byproducts
                if isinstance(item, dict) and item.get("name") == "buildx-result"
            ),
            None,
        )
        if not isinstance(buildx, dict) or not isinstance(buildx.get("content"), str):
            raise ImageReleaseEvidenceError("provenance Buildx result is missing")
        try:
            buildx_content = json.loads(base64.b64decode(buildx["content"], validate=True))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ImageReleaseEvidenceError("provenance Buildx result is invalid") from exc
        if not isinstance(buildx_content, dict):
            raise ImageReleaseEvidenceError("provenance Buildx result is invalid")
        if buildx_content.get("containerimage.digest") != image_digest:
            raise ImageReleaseEvidenceError("provenance Buildx digest drifted")
        sbom = next(
            (
                item
                for item in byproducts
                if isinstance(item, dict) and item.get("name") == "cyclonedx-sbom"
            ),
            None,
        )
        if not isinstance(sbom, dict) or sbom.get("digest") != {
            "sha256": sbom_sha256.removeprefix("sha256:")
        }:
            raise ImageReleaseEvidenceError("provenance SBOM digest drifted")
        predicate_types.add(predicate_type)
    return {
        "media_type": "application/vnd.dsse.envelope.v1+json",
        "sha256": _sha256(content),
        "verification_count": len(entries),
        "predicate_types": sorted(predicate_types),
        "subject": {"image_ref": image_ref, "image_digest": image_digest},
    }


def base_image_evidence_identity(
    *,
    inventory_path: Path,
    manifest_path: Path,
    dockerfile_path: str,
    verified_on: date | None = None,
) -> dict[str, Any]:
    """Bind lifecycle and linux/amd64 manifest evidence to the target Dockerfile."""
    inventory_content, inventory_raw = _json(inventory_path, name="base lifecycle inventory")
    manifest_content, manifest_raw = _json(manifest_path, name="base manifest evidence")
    inventory = _object(inventory_raw, name="base lifecycle inventory")
    manifest = _object(manifest_raw, name="base manifest evidence")
    if inventory.get("schema_version") != "lotus-core.base-image-lifecycle-inventory.v1":
        raise ImageReleaseEvidenceError("base lifecycle inventory version is invalid")
    if manifest.get("schema_version") != "lotus-core.base-image-manifest-evidence.v1":
        raise ImageReleaseEvidenceError("base manifest evidence version is invalid")
    candidates = inventory.get("base_images")
    if not isinstance(candidates, list):
        raise ImageReleaseEvidenceError("base lifecycle inventory images are invalid")
    matches = [
        item
        for item in candidates
        if isinstance(item, dict) and dockerfile_path in item.get("covered_dockerfiles", [])
    ]
    if len(matches) != 1:
        raise ImageReleaseEvidenceError("Dockerfile must map to exactly one base image")
    base = matches[0]
    verification_date = verified_on or datetime.now(UTC).date()
    observed_on = _iso_date(base.get("observed_on"), field="observed_on")
    next_review_on = _iso_date(base.get("next_review_on"), field="next_review_on")
    supported_through = _iso_date(base.get("supported_through"), field="supported_through")
    if observed_on > verification_date:
        raise ImageReleaseEvidenceError("base lifecycle observation is future-dated")
    if next_review_on < verification_date:
        raise ImageReleaseEvidenceError("base lifecycle review is overdue")
    if supported_through < verification_date:
        raise ImageReleaseEvidenceError("base image support lifecycle has expired")
    platform = manifest.get("deployment_platform")
    runtime_manifest = manifest.get("runtime_manifest")
    if platform != base.get("deployment_platform") or platform != "linux/amd64":
        raise ImageReleaseEvidenceError("base-image deployment architecture drifted")
    if not isinstance(runtime_manifest, dict):
        raise ImageReleaseEvidenceError("base runtime manifest identity is missing")
    if runtime_manifest.get("digest") != base.get("resolved_manifest_digest"):
        raise ImageReleaseEvidenceError("base runtime manifest digest drifted")
    if runtime_manifest.get("config_digest") != base.get("config_digest"):
        raise ImageReleaseEvidenceError("base runtime config digest drifted")
    if manifest.get("image") != base.get("image"):
        raise ImageReleaseEvidenceError("base image identity drifted")
    return {
        "inventory_sha256": _sha256(inventory_content),
        "manifest_evidence_sha256": _sha256(manifest_content),
        "dockerfile": dockerfile_path,
        "base_image": base["image"],
        "deployment_platform": platform,
        "runtime_manifest_digest": runtime_manifest["digest"],
        "config_digest": runtime_manifest["config_digest"],
        "observed_on": observed_on.isoformat(),
        "next_review_on": next_review_on.isoformat(),
        "supported_through": supported_through.isoformat(),
        "verified_on": verification_date.isoformat(),
    }
