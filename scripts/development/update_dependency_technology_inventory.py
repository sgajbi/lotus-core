"""Refresh the governed dependency technology inventory from exact PyPI release metadata."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.quality.technology_governance_identity import normalized_text_sha256

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "contracts" / "security" / "dependency-license-policy.v1.json"
INVENTORY_FILE = ROOT / "contracts" / "security" / "dependency-technology-inventory.v1.json"
LOCKS = (
    ("runtime", "linux/amd64", ROOT / "requirements" / "shared-runtime.lock.txt"),
    ("runtime", "windows/amd64", ROOT / "requirements" / "shared-runtime-windows.lock.txt"),
    ("ci_build_test", "linux/amd64", ROOT / "requirements" / "ci-tooling.lock.txt"),
    ("ci_build_test", "windows/amd64", ROOT / "requirements" / "ci-tooling-windows.lock.txt"),
)
PIN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$")
COMPOUND_LICENSE = re.compile(r"\s(?:AND|OR|WITH)\s", re.IGNORECASE)
GENERATOR_ID = "lotus-core-dependency-technology-inventory"
GENERATOR_VERSION = "1.2.0"


class InventoryRefreshError(RuntimeError):
    """Raised when authoritative package metadata cannot be refreshed safely."""


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _locked_components() -> tuple[list[dict[str, str]], dict[tuple[str, str], set[str]]]:
    locks: list[dict[str, str]] = []
    memberships: dict[tuple[str, str], set[str]] = {}
    for scope, platform, path in LOCKS:
        relative_path = path.relative_to(ROOT).as_posix()
        locks.append(
            {
                "path": relative_path,
                "scope": scope,
                "platform": platform,
                "sha256": normalized_text_sha256(path),
            }
        )
        for line in path.read_text(encoding="utf-8").splitlines():
            match = PIN.fullmatch(line.strip())
            if match:
                key = (_canonical_name(match.group("name")), match.group("version"))
                memberships.setdefault(key, set()).add(f"{scope}:{platform}")
    return locks, memberships


def _fetch_pypi(name: str, version: str) -> dict[str, Any]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{GENERATOR_ID}/{GENERATOR_VERSION}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise InventoryRefreshError(
            f"unable to fetch exact PyPI metadata for {name}=={version}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("info"), dict):
        raise InventoryRefreshError(f"invalid PyPI metadata shape for {name}=={version}")
    return payload


def _license_classification(info: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    declared = str(info.get("license_expression") or "").strip()
    legacy = str(info.get("license") or "").strip()
    classifiers = sorted(
        str(value) for value in info.get("classifiers", []) if str(value).startswith("License ::")
    )
    mapped_classifiers = sorted(
        {
            policy["classifier_mappings"][value]
            for value in classifiers
            if value in policy["classifier_mappings"]
        }
    )
    has_ambiguous_classifier = any(marker in classifiers for marker in policy["ambiguous_markers"])
    approved = set(policy["approved_single_spdx_expressions"])
    if declared:
        if COMPOUND_LICENSE.search(declared):
            status, reason = "review_required", "compound_declared_expression"
        elif has_ambiguous_classifier:
            status, reason = "review_required", "ambiguous_classifier_with_declared_expression"
        elif mapped_classifiers and set(mapped_classifiers) != {declared}:
            status, reason = "review_required", "conflicting_declared_and_classifier_metadata"
        elif declared in approved:
            status, reason = "approved", "approved_declared_expression"
        else:
            status, reason = "review_required", "unmapped_declared_expression"
        normalized: str | None = declared
        source = "pypi_license_expression"
    elif (
        legacy in policy["legacy_license_mappings"]
        and mapped_classifiers
        and set(mapped_classifiers) != {policy["legacy_license_mappings"][legacy]}
    ):
        normalized = None
        status, reason, source = (
            "review_required",
            "conflicting_legacy_and_classifier_metadata",
            "pypi_metadata",
        )
    elif len(mapped_classifiers) == 1 and not has_ambiguous_classifier:
        normalized = mapped_classifiers[0]
        status = "approved" if normalized in approved else "review_required"
        reason = "approved_classifier_mapping" if status == "approved" else "unapproved_classifier"
        source = "pypi_classifier_mapping"
    elif (
        legacy in policy["legacy_license_mappings"]
        and set(mapped_classifiers) in (set(), {policy["legacy_license_mappings"][legacy]})
        and not has_ambiguous_classifier
    ):
        normalized = policy["legacy_license_mappings"][legacy]
        status = "approved" if normalized in approved else "review_required"
        reason = "approved_legacy_mapping" if status == "approved" else "unapproved_legacy"
        source = "pypi_legacy_mapping"
    elif declared or legacy or classifiers:
        normalized = None
        status, reason, source = (
            "review_required",
            "ambiguous_or_unmapped_metadata",
            "pypi_metadata",
        )
    else:
        normalized = None
        status, reason, source = "blocked", "missing_license_metadata", "pypi_metadata"
    return {
        "declared_expression": declared or None,
        "legacy_value": legacy or None,
        "classifiers": classifiers,
        "normalized_expression": normalized,
        "classification": status,
        "classification_reason": reason,
        "classification_source": source,
    }


def _source_repository(info: dict[str, Any]) -> str | None:
    urls = {str(key).lower(): str(value) for key, value in (info.get("project_urls") or {}).items()}
    for key in ("source", "source code", "repository", "code", "github"):
        if urls.get(key):
            return urls[key]
    home_page = str(info.get("home_page") or "").strip()
    return home_page or None


def _release_timestamp(payload: dict[str, Any]) -> str | None:
    timestamps = sorted(
        str(item.get("upload_time_iso_8601"))
        for item in payload.get("urls", [])
        if item.get("upload_time_iso_8601")
    )
    return timestamps[0] if timestamps else None


def _source_commit() -> str:
    result = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_inventory(*, reviewed_on: date) -> dict[str, Any]:
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    locks, memberships = _locked_components()
    components: list[dict[str, Any]] = []
    for name, version in sorted(memberships):
        payload = _fetch_pypi(name, version)
        info = payload["info"]
        release_timestamp = _release_timestamp(payload)
        prerelease = bool(re.search(r"(?:a|b|rc|dev)\d*", version, re.IGNORECASE))
        yanked = bool(info.get("yanked"))
        source_repository = _source_repository(info)
        if prerelease:
            supportability = "blocked"
            supportability_reason = "prerelease_dependency"
        elif yanked:
            supportability = "blocked"
            supportability_reason = "yanked_dependency"
        elif not release_timestamp:
            supportability = "blocked"
            supportability_reason = "release_evidence_missing"
        else:
            supportability = "review_required"
            supportability_reason = "upstream_support_evidence_not_governed"
        components.append(
            {
                "name": name,
                "version": version,
                "lock_membership": sorted(memberships[(name, version)]),
                "pypi_release_url": f"https://pypi.org/project/{name}/{version}/",
                "pypi_json_url": f"https://pypi.org/pypi/{name}/{version}/json",
                "pypi_metadata_sha256": _sha256_bytes(_canonical_json(payload)),
                "release_uploaded_at": release_timestamp,
                "requires_python": info.get("requires_python"),
                "source_repository_url": source_repository,
                "yanked": yanked,
                "prerelease": prerelease,
                "license": _license_classification(info, policy),
                "supportability": {
                    "classification": supportability,
                    "classification_reason": supportability_reason,
                    "support_model": "upstream_release_evidence_plus_lotus_internal_lifecycle",
                    "release_evidence_url": f"https://pypi.org/project/{name}/{version}/",
                    "upstream_support_policy_url": None,
                    "vulnerability_disclosure_url": None,
                    "reviewed_on": reviewed_on.isoformat(),
                    "next_review_due": (
                        reviewed_on + timedelta(days=int(policy["review_cadence_days"]))
                    ).isoformat(),
                    "eol_evidence_url": None,
                    "approval_inference": "none",
                },
            }
        )
    approved_license_count = sum(
        component["license"]["classification"] == "approved" for component in components
    )
    blocked_component_count = sum(
        component["license"]["classification"] != "approved"
        or component["supportability"]["classification"] != "reviewed"
        for component in components
    )
    generated_at = (
        datetime.combine(reviewed_on, datetime.min.time(), UTC).isoformat().replace("+00:00", "Z")
    )
    return {
        "schema_version": "lotus-core.dependency-technology-inventory.v1",
        "inventory_id": "lotus-core-python-dependency-technology-inventory",
        "governed_by_issue": "https://github.com/sgajbi/lotus-core/issues/926",
        "repository": "https://github.com/sgajbi/lotus-core",
        "source_baseline_commit": _source_commit(),
        "generated_at_utc": generated_at,
        "generator": {"id": GENERATOR_ID, "version": GENERATOR_VERSION},
        "policy": {
            "path": POLICY_FILE.relative_to(ROOT).as_posix(),
            "sha256": normalized_text_sha256(POLICY_FILE),
        },
        "claim_boundary": {
            "technology_state": (
                "non_certifying" if blocked_component_count else "approved_default_candidate"
            ),
            "production_ready_claim": False,
            "bank_buyable_claim": False,
            "popularity_based_approval": False,
        },
        "support_model": {
            "owner": "Lotus Technology Risk and Open Source Governance",
            "review_cadence_days": int(policy["review_cadence_days"]),
            "vulnerability_evaluator": "pip-audit==2.10.1 against the installed exact lock closure",
            "posture": (
                "Lotus owns operational support and removal decisions; upstream release metadata "
                "is evidence, not an inferred support promise."
            ),
        },
        "source_locks": locks,
        "summary": {
            "component_count": len(components),
            "approved_license_count": approved_license_count,
            "blocked_or_review_required_count": blocked_component_count,
            "certification_decision": "blocked" if blocked_component_count else "allowed",
        },
        "components": components,
    }


def main() -> int:
    reviewed_on = date.fromisoformat(
        os.getenv("LOTUS_INVENTORY_REVIEW_DATE", date.today().isoformat())
    )
    inventory = build_inventory(reviewed_on=reviewed_on)
    INVENTORY_FILE.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "component_count": inventory["summary"]["component_count"],
                "decision": inventory["summary"]["certification_decision"],
                "output": INVENTORY_FILE.relative_to(ROOT).as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
