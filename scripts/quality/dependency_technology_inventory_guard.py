"""Validate locked dependency technology evidence and emit an exact-execution receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.quality.technology_governance_identity import normalized_text_sha256

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = ROOT / "contracts" / "security" / "dependency-technology-inventory.v1.json"
DEFAULT_OUTPUT = ROOT / "output" / "dependency-technology" / "inventory-receipt.json"
PIN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$")
REQUIRED_SOURCE_LOCKS = frozenset(
    {
        ("requirements/shared-runtime.lock.txt", "runtime", "linux/amd64"),
        ("requirements/shared-runtime-windows.lock.txt", "runtime", "windows/amd64"),
        ("requirements/ci-tooling.lock.txt", "ci_build_test", "linux/amd64"),
        ("requirements/ci-tooling-windows.lock.txt", "ci_build_test", "windows/amd64"),
    }
)
PYPI_USER_AGENT = "lotus-core-dependency-technology-certifier/1.0.0"
INVENTORY_SCHEMA_VERSION = "lotus-core.dependency-technology-inventory.v1"
INVENTORY_ID = "lotus-core-python-dependency-technology-inventory"
INVENTORY_REPOSITORY = "https://github.com/sgajbi/lotus-core"
INVENTORY_ISSUE = "https://github.com/sgajbi/lotus-core/issues/926"
INVENTORY_GENERATOR = {
    "id": "lotus-core-dependency-technology-inventory",
    "version": "1.0.0",
}


class InventoryValidationError(RuntimeError):
    """Raised when dependency technology evidence is incomplete or has drifted."""


def _is_governed_authority_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fetch_pypi_metadata(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": PYPI_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise InventoryValidationError(f"unable to revalidate PyPI authority: {url}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("info"), dict):
        raise InventoryValidationError(f"invalid PyPI authority response: {url}")
    return payload


def _verify_pypi_authority(component: dict[str, Any], component_id: str) -> None:
    payload = _fetch_pypi_metadata(str(component["pypi_json_url"]))
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if digest != component["pypi_metadata_sha256"]:
        raise InventoryValidationError(f"PyPI metadata digest drift: {component_id}")
    info = payload["info"]
    release_timestamps = sorted(
        str(item.get("upload_time_iso_8601"))
        for item in payload.get("urls", [])
        if item.get("upload_time_iso_8601")
    )
    expected_license = {
        "declared_expression": str(info.get("license_expression") or "").strip() or None,
        "legacy_value": str(info.get("license") or "").strip() or None,
        "classifiers": sorted(
            str(value)
            for value in info.get("classifiers", [])
            if str(value).startswith("License ::")
        ),
    }
    recorded_license = component["license"]
    if any(recorded_license.get(field) != value for field, value in expected_license.items()):
        raise InventoryValidationError(f"PyPI license evidence drift: {component_id}")
    expected_uploaded_at = release_timestamps[0] if release_timestamps else None
    if component.get("release_uploaded_at") != expected_uploaded_at:
        raise InventoryValidationError(f"PyPI release timestamp drift: {component_id}")
    if component.get("yanked") is not bool(info.get("yanked")):
        raise InventoryValidationError(f"PyPI yanked evidence drift: {component_id}")


def _validate_approved_license(
    license_evidence: dict[str, Any], policy: dict[str, Any], component: str
) -> None:
    normalized = license_evidence.get("normalized_expression")
    if normalized not in set(policy["approved_single_spdx_expressions"]):
        raise InventoryValidationError(f"approved license is outside policy: {component}")
    source = license_evidence.get("classification_source")
    reason = license_evidence.get("classification_reason")
    if source == "pypi_license_expression":
        mapped_classifiers = {
            policy["classifier_mappings"][classifier]
            for classifier in license_evidence.get("classifiers", [])
            if classifier in policy["classifier_mappings"]
        }
        evidence_matches = (
            reason == "approved_declared_expression"
            and license_evidence.get("declared_expression") == normalized
            and mapped_classifiers in (set(), {normalized})
            and not any(
                marker in license_evidence.get("classifiers", [])
                for marker in policy["ambiguous_markers"]
            )
        )
    elif source == "pypi_classifier_mapping":
        mapped = {
            policy["classifier_mappings"][classifier]
            for classifier in license_evidence.get("classifiers", [])
            if classifier in policy["classifier_mappings"]
        }
        evidence_matches = (
            reason == "approved_classifier_mapping"
            and mapped == {normalized}
            and not any(
                marker in license_evidence.get("classifiers", [])
                for marker in policy["ambiguous_markers"]
            )
        )
    elif source == "pypi_legacy_mapping":
        legacy_mapping = policy["legacy_license_mappings"].get(license_evidence.get("legacy_value"))
        mapped_classifiers = {
            policy["classifier_mappings"][classifier]
            for classifier in license_evidence.get("classifiers", [])
            if classifier in policy["classifier_mappings"]
        }
        evidence_matches = (
            reason == "approved_legacy_mapping"
            and legacy_mapping == normalized
            and mapped_classifiers in (set(), {normalized})
            and not any(
                marker in license_evidence.get("classifiers", [])
                for marker in policy["ambiguous_markers"]
            )
        )
    else:
        evidence_matches = False
    if not evidence_matches:
        raise InventoryValidationError(f"approved license lacks policy evidence: {component}")


def _commit() -> str:
    candidate = os.getenv("GITHUB_SHA")
    if candidate and re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
        return candidate.lower()
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _commit_is_ancestor(candidate: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _validate_inventory_provenance(inventory: dict[str, Any], *, as_of: date) -> None:
    expected = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "inventory_id": INVENTORY_ID,
        "repository": INVENTORY_REPOSITORY,
        "governed_by_issue": INVENTORY_ISSUE,
        "generator": INVENTORY_GENERATOR,
    }
    for field, value in expected.items():
        if inventory.get(field) != value:
            raise InventoryValidationError(f"dependency inventory {field} provenance drift")
    source_commit = inventory.get("source_commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise InventoryValidationError("dependency inventory source_commit must be a full SHA")
    if not _commit_is_ancestor(source_commit):
        raise InventoryValidationError(
            "dependency inventory source_commit is not an ancestor of the inspected checkout"
        )
    generated_at = datetime.fromisoformat(
        str(inventory.get("generated_at_utc", "")).replace("Z", "+00:00")
    )
    if generated_at.tzinfo is None or generated_at.date() > as_of:
        raise InventoryValidationError("dependency inventory generation time is invalid")


def _expected_components(source_locks: list[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
    identities = [
        (str(lock["path"]), str(lock["scope"]), str(lock["platform"])) for lock in source_locks
    ]
    if len(identities) != len(set(identities)) or set(identities) != REQUIRED_SOURCE_LOCKS:
        raise InventoryValidationError(
            "source lock set drift: "
            f"expected={sorted(REQUIRED_SOURCE_LOCKS)}, actual={sorted(set(identities))}"
        )
    expected: dict[tuple[str, str], set[str]] = {}
    for lock in source_locks:
        path = ROOT / str(lock["path"])
        if not path.is_file() or normalized_text_sha256(path) != lock["sha256"]:
            raise InventoryValidationError(f"source lock drift: {lock['path']}")
        membership = f"{lock['scope']}:{lock['platform']}"
        for line in path.read_text(encoding="utf-8").splitlines():
            match = PIN.fullmatch(line.strip())
            if match:
                key = (_canonical_name(match.group("name")), match.group("version"))
                expected.setdefault(key, set()).add(membership)
    return expected


def _validate_inventory_claims(inventory: dict[str, Any], components: list[dict[str, Any]]) -> None:
    claim_boundary = inventory.get("claim_boundary")
    if not isinstance(claim_boundary, dict):
        raise InventoryValidationError("dependency inventory claim boundary is required")
    for field in (
        "production_ready_claim",
        "bank_buyable_claim",
        "popularity_based_approval",
    ):
        if claim_boundary.get(field) is not False:
            raise InventoryValidationError(f"dependency inventory prohibits {field}")

    approved_license_count = sum(
        component.get("license", {}).get("classification") == "approved" for component in components
    )
    blocked_component_count = sum(
        component.get("license", {}).get("classification") != "approved"
        or component.get("supportability", {}).get("classification") != "reviewed"
        for component in components
    )
    expected_summary = {
        "component_count": len(components),
        "approved_license_count": approved_license_count,
        "blocked_or_review_required_count": blocked_component_count,
        "certification_decision": "blocked" if blocked_component_count else "allowed",
    }
    if inventory.get("summary") != expected_summary:
        raise InventoryValidationError(
            "dependency inventory summary contradicts component evidence"
        )
    expected_technology_state = (
        "non_certifying" if blocked_component_count else "approved_default_candidate"
    )
    if claim_boundary.get("technology_state") != expected_technology_state:
        raise InventoryValidationError(
            "dependency inventory technology state contradicts component evidence"
        )


def validate_inventory(*, as_of: date, verify_pypi_authority: bool = False) -> dict[str, Any]:
    inventory = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
    _validate_inventory_provenance(inventory, as_of=as_of)
    components = inventory.get("components")
    if not isinstance(components, list):
        raise InventoryValidationError("dependency inventory components must be a list")
    _validate_inventory_claims(inventory, components)
    policy = inventory["policy"]
    policy_path = ROOT / str(policy["path"])
    if not policy_path.is_file() or normalized_text_sha256(policy_path) != policy["sha256"]:
        raise InventoryValidationError("dependency license policy identity has drifted")
    policy_contract = json.loads(policy_path.read_text(encoding="utf-8"))
    review_cadence_days = int(policy_contract["review_cadence_days"])
    if review_cadence_days < 1:
        raise InventoryValidationError("dependency review cadence must be positive")
    expected = _expected_components(inventory["source_locks"])
    actual: dict[tuple[str, str], dict[str, Any]] = {}
    findings: list[dict[str, str]] = []
    for component in components:
        key = (_canonical_name(str(component["name"])), str(component["version"]))
        if key in actual:
            raise InventoryValidationError(f"duplicate component: {key[0]}=={key[1]}")
        actual[key] = component
        if set(component["lock_membership"]) != expected.get(key, set()):
            raise InventoryValidationError(f"lock membership drift: {key[0]}=={key[1]}")
        license_state = str(component["license"]["classification"])
        support_state = str(component["supportability"]["classification"])
        supportability = component["supportability"]
        component_id = f"{key[0]}=={key[1]}"
        yanked = component.get("yanked")
        prerelease = component.get("prerelease")
        expected_prerelease = bool(re.search(r"(?:a|b|rc|dev)\d*", key[1], re.IGNORECASE))
        if not isinstance(yanked, bool) or not isinstance(prerelease, bool):
            raise InventoryValidationError(f"invalid release posture flags: {component_id}")
        if prerelease != expected_prerelease:
            raise InventoryValidationError(f"prerelease evidence drift: {component_id}")
        expected_release_url = f"https://pypi.org/project/{key[0]}/{key[1]}/"
        expected_json_url = f"https://pypi.org/pypi/{key[0]}/{key[1]}/json"
        if component.get("pypi_release_url") != expected_release_url:
            raise InventoryValidationError(f"PyPI release authority drift: {component_id}")
        if component.get("pypi_json_url") != expected_json_url:
            raise InventoryValidationError(f"PyPI JSON authority drift: {component_id}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(component.get("pypi_metadata_sha256", ""))):
            raise InventoryValidationError(f"invalid PyPI metadata digest: {component_id}")
        uploaded_at = datetime.fromisoformat(
            str(component["release_uploaded_at"]).replace("Z", "+00:00")
        )
        if uploaded_at.date() > as_of:
            raise InventoryValidationError(f"release evidence is future-dated: {component_id}")
        if supportability.get("release_evidence_url") != expected_release_url:
            raise InventoryValidationError(f"support release authority drift: {component_id}")
        if supportability.get("approval_inference") != "none":
            raise InventoryValidationError(
                f"support approval inference is prohibited: {component_id}"
            )
        if license_state == "approved":
            _validate_approved_license(component["license"], policy_contract, component_id)
        if support_state == "reviewed" and not all(
            _is_governed_authority_url(supportability.get(field))
            for field in (
                "upstream_support_policy_url",
                "vulnerability_disclosure_url",
                "eol_evidence_url",
            )
        ):
            raise InventoryValidationError(
                f"reviewed supportability lacks authority: {key[0]}=={key[1]}"
            )
        reviewed_on = date.fromisoformat(supportability["reviewed_on"])
        due = date.fromisoformat(supportability["next_review_due"])
        review_interval_days = (due - reviewed_on).days
        if reviewed_on > as_of:
            raise InventoryValidationError(
                f"supportability review is future-dated: {key[0]}=={key[1]}"
            )
        if review_interval_days < 1 or review_interval_days > review_cadence_days:
            raise InventoryValidationError(
                f"supportability review cadence drift: {key[0]}=={key[1]}"
            )
        if due < as_of:
            findings.append({"component": component_id, "reason": "review_stale"})
        if yanked:
            findings.append({"component": component_id, "reason": "release_yanked"})
        if prerelease:
            findings.append({"component": component_id, "reason": "release_prerelease"})
        if license_state != "approved":
            findings.append(
                {
                    "component": f"{key[0]}=={key[1]}",
                    "reason": f"license_{license_state}",
                }
            )
        if support_state != "reviewed":
            findings.append(
                {
                    "component": f"{key[0]}=={key[1]}",
                    "reason": f"supportability_{support_state}",
                }
            )
        for required in (
            "pypi_release_url",
            "pypi_json_url",
            "pypi_metadata_sha256",
            "release_uploaded_at",
        ):
            if not component.get(required):
                raise InventoryValidationError(f"missing {required}: {key[0]}=={key[1]}")
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise InventoryValidationError(
            f"component coverage drift: missing={missing}, extra={extra}"
        )
    authority_revalidated = False
    if not findings and verify_pypi_authority:
        for key, component in sorted(actual.items()):
            _verify_pypi_authority(component, f"{key[0]}=={key[1]}")
        authority_revalidated = True
    return {
        "schema_version": "lotus-core.dependency-technology-inventory-receipt.v1",
        "status": "passed",
        "certification_decision": (
            "allowed" if not findings and authority_revalidated else "blocked"
        ),
        "repository": "https://github.com/sgajbi/lotus-core",
        "source_commit": _commit(),
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_path": INVENTORY_FILE.relative_to(ROOT).as_posix(),
        "inventory_sha256": normalized_text_sha256(INVENTORY_FILE),
        "component_count": len(actual),
        "finding_count": len(findings),
        "findings": sorted(findings, key=lambda item: (item["component"], item["reason"])),
        "pypi_authority_revalidation": {
            "required_for_certification": True,
            "status": "passed" if authority_revalidated else "not_run",
        },
        "claim_boundary": {
            "release_certifying": not findings and authority_revalidated,
            "production_ready_claim": False,
            "bank_buyable_claim": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--enforce-allowed",
        action="store_true",
        help="Return non-zero when evidence is structurally valid but certification is blocked.",
    )
    args = parser.parse_args()
    exit_code = 0
    try:
        receipt = validate_inventory(
            as_of=args.as_of,
            verify_pypi_authority=args.enforce_allowed,
        )
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        InventoryValidationError,
    ) as exc:
        receipt = {
            "schema_version": "lotus-core.dependency-technology-inventory-receipt.v1",
            "status": "failed",
            "certification_decision": "unavailable",
            "repository": "https://github.com/sgajbi/lotus-core",
            "source_commit": _commit(),
            "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "inventory_path": INVENTORY_FILE.relative_to(ROOT).as_posix(),
            "failure_type": type(exc).__name__,
            "failure": str(exc),
            "claim_boundary": {
                "release_certifying": False,
                "production_ready_claim": False,
                "bank_buyable_claim": False,
            },
        }
        exit_code = 1
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in ("status", "certification_decision", "component_count", "finding_count")
                if key in receipt
            },
            sort_keys=True,
        )
    )
    if args.enforce_allowed and receipt["certification_decision"] != "allowed":
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
