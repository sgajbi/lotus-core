"""Validate immutable base-image support and release-boundary evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = Path("contracts/security/base-image-lifecycle-inventory.v1.json")
SCHEMA_VERSION = "lotus-core.base-image-lifecycle-inventory.v1"
INVENTORY_ID = "lotus-core-base-image-lifecycle"
IMMUTABLE_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
BASE_ARG_RE = re.compile(r"^ARG PYTHON_IMAGE=(?P<image>\S+)$", re.MULTILINE)
COMPOSE_IMAGE_RE = re.compile(r"^\s*image:\s*(?P<image>\S+)\s*$", re.MULTILINE)
REQUIRED_DEPLOYMENT_PLATFORM = "linux/amd64"


@dataclass(frozen=True)
class BaseImageLifecycleFinding:
    path: Path
    detail: str


def _parse_date(value: object, field: str, findings: list[str]) -> date | None:
    if not isinstance(value, str):
        findings.append(f"{field} must be an ISO date")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        findings.append(f"{field} must be an ISO date")
        return None


def _is_credential_free_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _external_compose_images(root: Path) -> set[str]:
    images: set[str] = set()
    for compose_file in sorted(root.glob("docker-compose*.yml")):
        content = compose_file.read_text(encoding="utf-8")
        for match in COMPOSE_IMAGE_RE.finditer(content):
            image = match.group("image")
            if image.startswith("lotus-core/") or "LOTUS_" in image:
                continue
            images.add(image)
    return images


def _validate_inventory(inventory: dict[str, Any], *, root: Path, today: date) -> list[str]:
    findings: list[str] = []
    if inventory.get("schema_version") != SCHEMA_VERSION:
        findings.append(f"schema_version must be {SCHEMA_VERSION}")
    if inventory.get("inventory_id") != INVENTORY_ID:
        findings.append(f"inventory_id must be {INVENTORY_ID}")

    records = inventory.get("base_images")
    if not isinstance(records, list) or len(records) != 1:
        findings.append("base_images must contain the single governed Core base image")
        return findings
    record = records[0]
    if not isinstance(record, dict):
        return [*findings, "base image record must be an object"]

    image = record.get("image")
    if not isinstance(image, str) or not IMMUTABLE_IMAGE_RE.fullmatch(image):
        findings.append("base image must use an immutable sha256 manifest-list digest")
    if record.get("maturity") != "stable":
        findings.append("base image maturity must be stable; experimental images are prohibited")
    if record.get("governance_classification") != "approved_default":
        findings.append("base image must be classified approved_default")
    if record.get("responsible_owner") != "lotus-core-maintainers":
        findings.append("base image must have the lotus-core-maintainers owner")

    observed_on = _parse_date(record.get("observed_on"), "observed_on", findings)
    next_review_on = _parse_date(record.get("next_review_on"), "next_review_on", findings)
    supported_through = _parse_date(record.get("supported_through"), "supported_through", findings)
    if observed_on and observed_on > today:
        findings.append("observed_on cannot be in the future")
    if next_review_on and next_review_on < today:
        findings.append("base-image lifecycle evidence is stale")
    if supported_through and supported_through < today:
        findings.append("base image runtime or distribution is end-of-life")
    max_review_days = record.get("max_review_interval_days")
    if not isinstance(max_review_days, int) or not 1 <= max_review_days <= 92:
        findings.append("max_review_interval_days must be between 1 and 92")
    elif observed_on and next_review_on:
        interval = (next_review_on - observed_on).days
        if interval <= 0 or interval > max_review_days:
            findings.append("next_review_on exceeds the governed review interval")
    if supported_through and next_review_on and next_review_on > supported_through:
        findings.append("next_review_on must precede the earliest support end date")

    if record.get("deployment_platform") != REQUIRED_DEPLOYMENT_PLATFORM:
        findings.append("deployment_platform must be the governed linux/amd64 target")
    for digest_field in ("resolved_manifest_digest", "config_digest"):
        value = record.get(digest_field)
        if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            findings.append(f"{digest_field} must be an immutable sha256 digest")
    available = record.get("index_runtime_platforms")
    if not isinstance(available, list) or REQUIRED_DEPLOYMENT_PLATFORM not in available:
        findings.append("index_runtime_platforms must include the governed deployment platform")
    metadata_count = record.get("metadata_manifest_count")
    if not isinstance(metadata_count, int) or metadata_count < 1:
        findings.append("metadata_manifest_count must distinguish attached metadata")
    if record.get("present_in_current_official_library") is not True:
        findings.append("base image tag must remain in the current Docker Official Images library")
    identity_evidence = record.get("identity_evidence")
    if not isinstance(identity_evidence, dict):
        findings.append("identity_evidence is required")
    else:
        for field in ("official_image_source", "official_image_registry"):
            if not _is_credential_free_https_url(identity_evidence.get(field)):
                findings.append(
                    f"identity_evidence.{field} must be a credential-free HTTPS authority"
                )
        verified_command = identity_evidence.get("verified_command")
        if not isinstance(verified_command, str) or not verified_command.strip():
            findings.append("identity_evidence.verified_command must be non-empty")
        elif isinstance(image, str) and image not in verified_command:
            findings.append("Official Images identity command must bind the governed image")
        identity_verified_on = _parse_date(
            identity_evidence.get("verified_on"), "identity_evidence.verified_on", findings
        )
        if identity_verified_on and identity_verified_on > today:
            findings.append("Official Images identity evidence cannot be future-dated")
        if observed_on and identity_verified_on and identity_verified_on != observed_on:
            findings.append("Official Images identity evidence must be refreshed with observed_on")

    components = record.get("support_components")
    if not isinstance(components, list) or {
        item.get("component") for item in components if isinstance(item, dict)
    } != {"cpython", "debian"}:
        findings.append("support_components must classify CPython and Debian")
    else:
        component_ends: list[date] = []
        for component in components:
            component_id = str(component.get("component", "unknown"))
            authority_end = _parse_date(
                component.get("authority_support_end_on"),
                f"support_components.{component_id}.authority_support_end_on",
                findings,
            )
            end = _parse_date(
                component.get("local_fail_closed_cutoff"),
                f"support_components.{component_id}.local_fail_closed_cutoff",
                findings,
            )
            if end:
                component_ends.append(end)
                if end < today:
                    findings.append(f"support component {component_id} is end-of-life")
                if authority_end and end > authority_end:
                    findings.append(
                        f"support component {component_id} local cutoff exceeds upstream authority"
                    )
            if authority_end and authority_end < today:
                findings.append(f"support component {component_id} upstream authority has ended")
            source = component.get("source")
            if not _is_credential_free_https_url(source):
                findings.append(
                    f"support component {component_id} requires a credential-free HTTPS authority"
                )
        if supported_through and component_ends and supported_through != min(component_ends):
            findings.append("supported_through must equal the earliest component support end date")

    package_support = record.get("distribution_package_support")
    if not isinstance(package_support, dict):
        findings.append("distribution_package_support evidence is required")
    else:
        if package_support.get("status") != "clean":
            findings.append("exact-image Debian package support status must be clean")
        if package_support.get("image") != image:
            findings.append("Debian package support evidence must bind the governed image")
        if package_support.get("deployment_platform") != REQUIRED_DEPLOYMENT_PLATFORM:
            findings.append("Debian package support evidence must bind linux/amd64")
        if not package_support.get("verified_command"):
            findings.append("Debian package support evidence requires its verified command")
        package_verified_on = _parse_date(
            package_support.get("verified_on"),
            "distribution_package_support.verified_on",
            findings,
        )
        if package_verified_on and package_verified_on > today:
            findings.append("Debian package support evidence cannot be future-dated")
        if observed_on and package_verified_on and package_verified_on != observed_on:
            findings.append("Debian package support evidence must be refreshed with observed_on")

    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / "src" / "services").rglob("Dockerfile")
    }
    covered = set(record.get("covered_dockerfiles", []))
    if covered != discovered:
        findings.append("covered_dockerfiles must exactly match all Core service Dockerfiles")
    if isinstance(image, str):
        for relative in sorted(discovered):
            content = (root / relative).read_text(encoding="utf-8")
            match = BASE_ARG_RE.search(content)
            if not match or match.group("image") != image:
                findings.append(f"{relative} does not use the governed base image")

    boundary = inventory.get("outside_release_boundary")
    expected_external = _external_compose_images(root)
    if not isinstance(boundary, dict):
        findings.append("outside_release_boundary must classify local dependency images")
    else:
        classified = set(boundary.get("local_compose_dependency_images", []))
        if classified != expected_external:
            findings.append(
                "outside_release_boundary.local_compose_dependency_images must exactly "
                "classify external Compose images"
            )
        if boundary.get("classification") != "local_validation_only":
            findings.append("external Compose images must be classified local_validation_only")
        if not boundary.get("rationale"):
            findings.append("outside-release-boundary classification requires a rationale")
    return findings


def find_base_image_lifecycle_findings(
    root: Path = REPO_ROOT, *, today: date | None = None
) -> list[BaseImageLifecycleFinding]:
    path = root / INVENTORY_PATH
    if not path.exists():
        return [BaseImageLifecycleFinding(INVENTORY_PATH, "missing lifecycle inventory")]
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [BaseImageLifecycleFinding(INVENTORY_PATH, f"invalid JSON: {exc}")]
    if not isinstance(inventory, dict):
        return [BaseImageLifecycleFinding(INVENTORY_PATH, "inventory root must be an object")]
    return [
        BaseImageLifecycleFinding(INVENTORY_PATH, detail)
        for detail in _validate_inventory(inventory, root=root, today=today or date.today())
    ]


def main() -> int:
    findings = find_base_image_lifecycle_findings()
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.detail}")
        return 1
    print("Base-image lifecycle inventory is current and covers the Core release boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
