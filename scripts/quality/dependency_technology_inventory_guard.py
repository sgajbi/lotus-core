"""Validate locked dependency technology evidence and emit an exact-execution receipt."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.quality.technology_governance_identity import normalized_text_sha256

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = ROOT / "contracts" / "security" / "dependency-technology-inventory.v1.json"
DEFAULT_OUTPUT = ROOT / "output" / "dependency-technology" / "inventory-receipt.json"
PIN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$")


class InventoryValidationError(RuntimeError):
    """Raised when dependency technology evidence is incomplete or has drifted."""


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _commit() -> str:
    candidate = os.getenv("GITHUB_SHA")
    if candidate and re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
        return candidate.lower()
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _expected_components(source_locks: list[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
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


def validate_inventory(*, as_of: date) -> dict[str, Any]:
    inventory = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
    policy = inventory["policy"]
    policy_path = ROOT / str(policy["path"])
    if not policy_path.is_file() or normalized_text_sha256(policy_path) != policy["sha256"]:
        raise InventoryValidationError("dependency license policy identity has drifted")
    expected = _expected_components(inventory["source_locks"])
    actual: dict[tuple[str, str], dict[str, Any]] = {}
    findings: list[dict[str, str]] = []
    for component in inventory["components"]:
        key = (_canonical_name(str(component["name"])), str(component["version"]))
        if key in actual:
            raise InventoryValidationError(f"duplicate component: {key[0]}=={key[1]}")
        actual[key] = component
        if set(component["lock_membership"]) != expected.get(key, set()):
            raise InventoryValidationError(f"lock membership drift: {key[0]}=={key[1]}")
        license_state = str(component["license"]["classification"])
        support_state = str(component["supportability"]["classification"])
        supportability = component["supportability"]
        if support_state == "reviewed" and not all(
            supportability.get(field)
            for field in (
                "upstream_support_policy_url",
                "vulnerability_disclosure_url",
                "eol_evidence_url",
            )
        ):
            raise InventoryValidationError(
                f"reviewed supportability lacks authority: {key[0]}=={key[1]}"
            )
        due = date.fromisoformat(component["supportability"]["next_review_due"])
        if due < as_of:
            findings.append({"component": f"{key[0]}=={key[1]}", "reason": "review_stale"})
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
    return {
        "schema_version": "lotus-core.dependency-technology-inventory-receipt.v1",
        "status": "passed",
        "certification_decision": "blocked" if findings else "allowed",
        "repository": "https://github.com/sgajbi/lotus-core",
        "source_commit": _commit(),
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_path": INVENTORY_FILE.relative_to(ROOT).as_posix(),
        "inventory_sha256": normalized_text_sha256(INVENTORY_FILE),
        "component_count": len(actual),
        "finding_count": len(findings),
        "findings": sorted(findings, key=lambda item: (item["component"], item["reason"])),
        "claim_boundary": {
            "release_certifying": not findings,
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
        receipt = validate_inventory(as_of=args.as_of)
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
