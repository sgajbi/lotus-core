"""Create, transport, and verify exact-source Docker image sets for CI runtime gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.ci_service_sets import PREBUILD_GROUPS  # noqa: E402
from scripts.release.prebuild_ci_images import SERVICE_BUILDS  # noqa: E402

SCHEMA_VERSION = "lotus-core.runtime-image-set.v1"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
DEPENDENCY_LOCK_FILE = REPO_ROOT / "requirements" / "shared-runtime.lock.txt"
FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
OCI_LABEL_FIELDS = {
    "org.opencontainers.image.revision": "source_commit_sha",
    "org.opencontainers.image.ref.name": "source_branch",
    "org.opencontainers.image.source": "repository_url",
    "org.opencontainers.image.version": "source_commit_sha",
    "org.opencontainers.image.ci.run_id": "ci_run_id",
}

Runner = Callable[..., subprocess.CompletedProcess[str]]


class RuntimeImageSetError(RuntimeError):
    """Raised when a runtime image set is incomplete, stale, or corrupted."""


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _require_source_metadata(metadata: dict[str, str]) -> None:
    if not FULL_GIT_SHA_PATTERN.fullmatch(metadata["source_commit_sha"]):
        raise RuntimeImageSetError("source commit must be a full lowercase Git SHA")
    for field in ("source_branch", "repository_url", "ci_run_id", "generated_at_utc"):
        if not metadata[field].strip() or metadata[field] == "unknown":
            raise RuntimeImageSetError(f"{field} is required")


def _inspect_image(
    image_tag: str,
    *,
    runner: Runner,
) -> dict[str, Any]:
    result = runner(
        ["docker", "image", "inspect", image_tag],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        inspections = json.loads(result.stdout)
        inspection = inspections[0]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        raise RuntimeImageSetError(f"invalid Docker inspection for {image_tag}") from exc
    if not isinstance(inspection, dict):
        raise RuntimeImageSetError(f"invalid Docker inspection for {image_tag}")
    return inspection


def _verify_image(
    *,
    service: dict[str, str],
    inspection: dict[str, Any],
    metadata: dict[str, str],
) -> None:
    image_tag = service["image_tag"]
    actual_image_id = str(inspection.get("Id", ""))
    if actual_image_id != service["image_id"]:
        raise RuntimeImageSetError(
            f"image id mismatch for {image_tag}: expected {service['image_id']}, "
            f"found {actual_image_id or 'missing'}"
        )
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    for label, metadata_field in OCI_LABEL_FIELDS.items():
        expected = metadata[metadata_field]
        actual = labels.get(label)
        if actual != expected:
            raise RuntimeImageSetError(
                f"OCI label mismatch for {image_tag}: {label} expected {expected}, "
                f"found {actual or 'missing'}"
            )
    created = labels.get("org.opencontainers.image.created")
    if not created or created == "unknown":
        raise RuntimeImageSetError(
            f"OCI label mismatch for {image_tag}: org.opencontainers.image.created is required"
        )


def _manifest_content_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"content_hash", "generated_at_utc"}
    }


def _content_hash(manifest: dict[str, Any]) -> str:
    return _sha256_bytes(_canonical_json(_manifest_content_payload(manifest)))


def _dependency_closure_hash(
    *,
    compose_file_sha256: str,
    dependency_lock_sha256: str,
    services: list[dict[str, str]],
) -> str:
    return _sha256_bytes(
        _canonical_json(
            {
                "compose_file_sha256": compose_file_sha256,
                "dependency_lock_sha256": dependency_lock_sha256,
                "services": services,
            }
        )
    )


def _service_records(
    services: Sequence[str],
    *,
    metadata: dict[str, str],
    runner: Runner,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for service in sorted(set(services)):
        if service not in SERVICE_BUILDS:
            raise RuntimeImageSetError(f"unknown service: {service}")
        image_tag, dockerfile = SERVICE_BUILDS[service]
        dockerfile_path = _resolve_path(dockerfile)
        inspection = _inspect_image(image_tag, runner=runner)
        image_id = str(inspection.get("Id", ""))
        if not SHA256_PATTERN.fullmatch(image_id):
            raise RuntimeImageSetError(f"invalid image id for {image_tag}: {image_id or 'missing'}")
        record = {
            "service": service,
            "image_tag": image_tag,
            "image_id": image_id,
            "dockerfile": str(dockerfile),
            "dockerfile_sha256": _sha256_file(dockerfile_path),
        }
        _verify_image(service=record, inspection=inspection, metadata=metadata)
        records.append(record)
    return records


def create_runtime_image_set(
    *,
    services: Sequence[str],
    manifest_path: Path,
    bundle_path: Path,
    source_commit_sha: str,
    source_branch: str,
    repository_url: str,
    ci_run_id: str,
    generated_at_utc: str | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Export locally built images and write their source-owned integrity manifest."""

    metadata = {
        "source_commit_sha": source_commit_sha,
        "source_branch": source_branch,
        "repository_url": repository_url,
        "ci_run_id": ci_run_id,
        "generated_at_utc": generated_at_utc
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    _require_source_metadata(metadata)
    records = _service_records(services, metadata=metadata, runner=runner)
    if not records:
        raise RuntimeImageSetError("at least one runtime image service is required")

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    runner(
        [
            "docker",
            "image",
            "save",
            "--output",
            str(bundle_path),
            *(record["image_tag"] for record in records),
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    if not bundle_path.is_file() or bundle_path.stat().st_size == 0:
        raise RuntimeImageSetError("Docker image bundle was not created")

    compose_file_sha256 = _sha256_file(COMPOSE_FILE)
    dependency_lock_sha256 = _sha256_file(DEPENDENCY_LOCK_FILE)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        **metadata,
        "service_count": len(records),
        "compose_file_sha256": compose_file_sha256,
        "dependency_lock_sha256": dependency_lock_sha256,
        "dependency_closure_hash": _dependency_closure_hash(
            compose_file_sha256=compose_file_sha256,
            dependency_lock_sha256=dependency_lock_sha256,
            services=records,
        ),
        "bundle_sha256": _sha256_file(bundle_path),
        "services": records,
    }
    manifest["content_hash"] = _content_hash(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_and_verify_runtime_image_set(
    *,
    manifest_path: Path,
    bundle_path: Path,
    expected_commit_sha: str,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Load an image bundle and fail closed unless its manifest and images match source."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeImageSetError(
            f"unable to read runtime image manifest: {manifest_path}"
        ) from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeImageSetError("unsupported runtime image manifest schema")
    if manifest.get("source_commit_sha") != expected_commit_sha:
        raise RuntimeImageSetError(
            "runtime image source commit mismatch: "
            f"expected {expected_commit_sha}, found {manifest.get('source_commit_sha', 'missing')}"
        )
    if _sha256_file(bundle_path) != manifest.get("bundle_sha256"):
        raise RuntimeImageSetError("runtime image bundle digest mismatch")
    if _content_hash(manifest) != manifest.get("content_hash"):
        raise RuntimeImageSetError("runtime image manifest content hash mismatch")
    services = manifest.get("services")
    if not isinstance(services, list) or not services:
        raise RuntimeImageSetError("runtime image manifest has no services")
    if manifest.get("compose_file_sha256") != _sha256_file(COMPOSE_FILE):
        raise RuntimeImageSetError("runtime image compose contract mismatch")
    if manifest.get("dependency_lock_sha256") != _sha256_file(DEPENDENCY_LOCK_FILE):
        raise RuntimeImageSetError("runtime image dependency lock mismatch")
    expected_closure_hash = _dependency_closure_hash(
        compose_file_sha256=str(manifest["compose_file_sha256"]),
        dependency_lock_sha256=str(manifest["dependency_lock_sha256"]),
        services=services,
    )
    if manifest.get("dependency_closure_hash") != expected_closure_hash:
        raise RuntimeImageSetError("runtime image dependency closure mismatch")

    runner(
        ["docker", "image", "load", "--input", str(bundle_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = {
        field: str(manifest.get(field, ""))
        for field in (
            "source_commit_sha",
            "source_branch",
            "repository_url",
            "ci_run_id",
            "generated_at_utc",
        )
    }
    _require_source_metadata(metadata)
    for service in services:
        if not isinstance(service, dict):
            raise RuntimeImageSetError("runtime image manifest contains an invalid service record")
        inspection = _inspect_image(str(service.get("image_tag", "")), runner=runner)
        _verify_image(service=service, inspection=inspection, metadata=metadata)
    return manifest


def _services_from_args(args: argparse.Namespace) -> list[str]:
    services = list(args.services or [])
    if args.group:
        services.extend(PREBUILD_GROUPS[args.group])
    return list(dict.fromkeys(services))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Export images and write a manifest.")
    create.add_argument("--services", nargs="*")
    create.add_argument("--group", choices=sorted(PREBUILD_GROUPS))
    create.add_argument("--manifest", type=Path, required=True)
    create.add_argument("--bundle", type=Path, required=True)
    create.add_argument("--source-commit-sha", required=True)
    create.add_argument("--source-branch", required=True)
    create.add_argument("--repository-url", required=True)
    create.add_argument("--ci-run-id", required=True)
    create.add_argument("--generated-at-utc")

    verify = subparsers.add_parser("load-verify", help="Load and verify a runtime image set.")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--expected-commit-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "create":
        create_runtime_image_set(
            services=_services_from_args(args),
            manifest_path=args.manifest,
            bundle_path=args.bundle,
            source_commit_sha=args.source_commit_sha,
            source_branch=args.source_branch,
            repository_url=args.repository_url,
            ci_run_id=args.ci_run_id,
            generated_at_utc=args.generated_at_utc,
        )
        return 0
    load_and_verify_runtime_image_set(
        manifest_path=args.manifest,
        bundle_path=args.bundle,
        expected_commit_sha=args.expected_commit_sha,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
