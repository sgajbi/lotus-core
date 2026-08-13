"""Refresh digest-verifiable OCI manifest evidence for the governed Core base image."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_INVENTORY = (
    REPO_ROOT / "contracts" / "security" / "base-image-lifecycle-inventory.v1.json"
)
EVIDENCE_PATH = REPO_ROOT / "contracts" / "security" / "base-image-manifest-evidence.v1.json"
SCHEMA_VERSION = "lotus-core.base-image-manifest-evidence.v1"
EVIDENCE_ID = "lotus-core-python-base-image-manifest-evidence"
GENERATOR_ID = "lotus-core-base-image-manifest-evidence"
GENERATOR_VERSION = "1.0.0"
REGISTRY_API_AUTHORITIES = {"docker.io": "https://registry-1.docker.io"}


class ManifestEvidenceRefreshError(RuntimeError):
    """Raised when the registry cannot supply internally consistent OCI evidence."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(value: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestEvidenceRefreshError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ManifestEvidenceRefreshError(f"{label} must be a JSON object")
    return payload


def _inspect_raw(reference: str) -> bytes:
    try:
        result = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", "--raw", reference],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestEvidenceRefreshError(f"unable to inspect OCI reference {reference}") from exc
    if not result.stdout:
        raise ManifestEvidenceRefreshError(f"OCI inspection returned no evidence for {reference}")
    return result.stdout


def _digest_from_reference(reference: str) -> str:
    marker = "@sha256:"
    if marker not in reference:
        raise ManifestEvidenceRefreshError("governed base image must be digest pinned")
    return "sha256:" + reference.rsplit(marker, maxsplit=1)[1]


def _select_platform_manifest(index: dict[str, Any], platform: str) -> dict[str, Any]:
    os_name, architecture = platform.split("/", maxsplit=1)
    matches = [
        item
        for item in index.get("manifests", [])
        if isinstance(item, dict)
        and item.get("platform") == {"architecture": architecture, "os": os_name}
    ]
    if len(matches) != 1:
        raise ManifestEvidenceRefreshError(
            f"OCI index must contain exactly one {platform} runtime manifest"
        )
    return matches[0]


def build_evidence() -> dict[str, Any]:
    lifecycle = json.loads(LIFECYCLE_INVENTORY.read_text(encoding="utf-8"))
    record = lifecycle["base_images"][0]
    image = str(record["image"])
    platform = str(record["deployment_platform"])
    parent_digest = _digest_from_reference(image)
    registry_authority = REGISTRY_API_AUTHORITIES.get(str(record.get("registry", "")))
    if registry_authority is None:
        raise ManifestEvidenceRefreshError(
            "governed base image registry has no approved OCI API authority"
        )

    index_bytes = _inspect_raw(image)
    if f"sha256:{_sha256(index_bytes)}" != parent_digest:
        raise ManifestEvidenceRefreshError(
            "registry index bytes do not match governed image digest"
        )
    index = _load_json(index_bytes, label="OCI index")
    child_descriptor = _select_platform_manifest(index, platform)
    child_digest = str(child_descriptor.get("digest", ""))

    repository = image.split("@", maxsplit=1)[0]
    child_reference = f"{repository}@{child_digest}"
    child_bytes = _inspect_raw(child_reference)
    if f"sha256:{_sha256(child_bytes)}" != child_digest:
        raise ManifestEvidenceRefreshError("registry child bytes do not match index descriptor")
    child = _load_json(child_bytes, label="OCI child manifest")
    config = child.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("digest"), str):
        raise ManifestEvidenceRefreshError("OCI child manifest does not identify a config digest")

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": EVIDENCE_ID,
        "image": image,
        "deployment_platform": platform,
        "observed_on": record["observed_on"],
        "generator": {"id": GENERATOR_ID, "version": GENERATOR_VERSION},
        "inspection": {
            "tool": "docker buildx imagetools inspect --raw",
            "parent_reference": image,
            "child_reference": child_reference,
        },
        "authority": {
            "registry": registry_authority,
            "repository": str(record["repository"]),
        },
        "index": {
            "digest": parent_digest,
            "media_type": index.get("mediaType"),
            "raw_base64": base64.b64encode(index_bytes).decode("ascii"),
        },
        "runtime_manifest": {
            "digest": child_digest,
            "media_type": child_descriptor.get("mediaType"),
            "size": child_descriptor.get("size"),
            "config_digest": config["digest"],
            "raw_base64": base64.b64encode(child_bytes).decode("ascii"),
        },
    }


def _serialized(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = _serialized(build_evidence())
    if args.check:
        if not EVIDENCE_PATH.exists() or EVIDENCE_PATH.read_text(encoding="utf-8") != expected:
            raise SystemExit(
                "Base-image manifest evidence is stale; run "
                "python scripts/development/update_base_image_manifest_evidence.py"
            )
        print("Base-image manifest evidence matches the authoritative OCI registry bytes.")
        return 0
    EVIDENCE_PATH.write_text(expected, encoding="utf-8")
    print(f"Wrote {EVIDENCE_PATH.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
