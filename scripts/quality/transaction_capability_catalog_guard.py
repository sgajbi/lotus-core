"""Validate transaction and product-lifecycle capability publication against code truth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path("contracts/transaction-processing/transaction-capability-catalog.v1.json")
REGISTRY_PATH = Path("src/libs/portfolio-common/portfolio_common/transaction_type_registry.py")
EXPECTED_SCHEMA_VERSION = "lotus-core-transaction-capability-catalog.v1"
GUARD_COMMAND = "make transaction-capability-catalog-guard"
ISSUE_REQUIRED_TRANSACTION_STATUSES = {
    "default_strategy",
    "limited",
    "migration_only",
    "target_not_implemented",
}
ALLOWED_PRODUCT_STATUSES = {
    "supported",
    "supported_via_generic_transaction_semantics",
    "limited",
    "target_not_implemented",
    "internal_only",
    "out_of_scope",
}
ISSUE_REQUIRED_PRODUCT_STATUSES = {"limited", "target_not_implemented"}


@dataclass(frozen=True, slots=True)
class TransactionCapabilityFinding:
    """Describe one deterministic catalog governance failure."""

    location: str
    detail: str


def _load_catalog(root: Path) -> dict[str, Any] | None:
    path = root / CATALOG_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_issue_numbers(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(issue_number, int) and issue_number > 0 for issue_number in value)
    )


def _validate_transaction_types(
    *,
    findings: list[TransactionCapabilityFinding],
    entries: object,
    registry: Mapping[str, object],
) -> None:
    if not isinstance(entries, list) or not entries:
        findings.append(TransactionCapabilityFinding("transaction_types", "must be non-empty"))
        return

    codes = [str(entry.get("code") or "") for entry in entries if isinstance(entry, dict)]
    for code in sorted({code for code in codes if codes.count(code) > 1}):
        findings.append(
            TransactionCapabilityFinding("transaction_types", f"duplicate transaction type {code}")
        )
    missing = sorted(set(registry) - set(codes))
    unexpected = sorted(set(codes) - set(registry))
    if missing:
        findings.append(
            TransactionCapabilityFinding(
                "transaction_types", f"missing registry transaction types: {', '.join(missing)}"
            )
        )
    if unexpected:
        findings.append(
            TransactionCapabilityFinding(
                "transaction_types", f"unknown transaction types: {', '.join(unexpected)}"
            )
        )

    for entry in entries:
        if not isinstance(entry, dict):
            findings.append(
                TransactionCapabilityFinding("transaction_types", "entry must be object")
            )
            continue
        code = str(entry.get("code") or "<missing-code>")
        definition = registry.get(code)
        if definition is None:
            continue
        expected_fields = {
            "lifecycle_family": getattr(definition, "lifecycle_family"),
            "economic_role": getattr(definition, "economic_role"),
            "support_status": getattr(definition, "calculation_support_status"),
            "production_booking_allowed": getattr(definition, "production_booking_allowed"),
        }
        for field_name, expected in expected_fields.items():
            if entry.get(field_name) != expected:
                findings.append(
                    TransactionCapabilityFinding(
                        code,
                        f"{field_name} must match registry value {expected!r}",
                    )
                )
        if entry.get("support_status") in ISSUE_REQUIRED_TRANSACTION_STATUSES and not isinstance(
            entry.get("gap_issue"), int
        ):
            findings.append(
                TransactionCapabilityFinding(
                    code,
                    f"{entry.get('support_status')} transaction requires gap_issue",
                )
            )


def _validate_product_lifecycles(
    *,
    findings: list[TransactionCapabilityFinding],
    entries: object,
    root: Path,
    registry: Mapping[str, object],
) -> None:
    if not isinstance(entries, list) or not entries:
        findings.append(TransactionCapabilityFinding("product_lifecycles", "must be non-empty"))
        return
    identities: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        location = f"product_lifecycles[{index}]"
        if not isinstance(entry, dict):
            findings.append(TransactionCapabilityFinding(location, "entry must be object"))
            continue
        product_family = str(entry.get("product_family") or "")
        lifecycle_event = str(entry.get("lifecycle_event") or "")
        identity = (product_family, lifecycle_event)
        if not all(identity):
            findings.append(
                TransactionCapabilityFinding(
                    location, "product_family and lifecycle_event required"
                )
            )
        elif identity in identities:
            findings.append(
                TransactionCapabilityFinding(location, f"duplicate product lifecycle {identity}")
            )
        identities.add(identity)

        status = entry.get("support_status")
        if status not in ALLOWED_PRODUCT_STATUSES:
            findings.append(
                TransactionCapabilityFinding(location, f"unsupported support_status {status!r}")
            )
        if status in ISSUE_REQUIRED_PRODUCT_STATUSES and not _valid_issue_numbers(
            entry.get("gap_issues")
        ):
            findings.append(
                TransactionCapabilityFinding(location, f"{status} lifecycle requires gap_issues")
            )

        transaction_types = entry.get("transaction_types")
        if not isinstance(transaction_types, list):
            findings.append(
                TransactionCapabilityFinding(location, "transaction_types must be list")
            )
        else:
            unknown = sorted(set(transaction_types) - set(registry))
            if unknown:
                findings.append(
                    TransactionCapabilityFinding(
                        location, f"unknown transaction types: {', '.join(unknown)}"
                    )
                )

        for field_name in ("evidence_refs", "limitations"):
            values = entry.get(field_name)
            if not isinstance(values, list) or not values:
                findings.append(
                    TransactionCapabilityFinding(location, f"{field_name} must be non-empty")
                )
                continue
            if field_name == "evidence_refs":
                for reference in values:
                    if not isinstance(reference, str) or not (root / reference).exists():
                        findings.append(
                            TransactionCapabilityFinding(
                                location, f"evidence reference does not exist: {reference!r}"
                            )
                        )


def _validate_documentation_surfaces(
    *,
    findings: list[TransactionCapabilityFinding],
    root: Path,
    surfaces: object,
) -> None:
    if not isinstance(surfaces, list) or not surfaces:
        findings.append(TransactionCapabilityFinding("documentation_surfaces", "must be non-empty"))
        return
    for relative_path in surfaces:
        location = str(relative_path)
        path = root / location
        if not path.exists():
            findings.append(TransactionCapabilityFinding(location, "documentation surface missing"))
            continue
        text = path.read_text(encoding="utf-8")
        if CATALOG_PATH.as_posix() not in text:
            findings.append(TransactionCapabilityFinding(location, "missing catalog reference"))
        if GUARD_COMMAND not in text:
            findings.append(TransactionCapabilityFinding(location, "missing guard command"))


def find_transaction_capability_findings(
    root: Path = REPO_ROOT,
    *,
    registry: Mapping[str, object] = TRANSACTION_TYPE_REGISTRY,
) -> list[TransactionCapabilityFinding]:
    """Return catalog drift and publication findings for the supplied repository root."""

    payload = _load_catalog(root)
    if payload is None:
        return [TransactionCapabilityFinding(CATALOG_PATH.as_posix(), "catalog is missing")]
    findings: list[TransactionCapabilityFinding] = []
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        findings.append(
            TransactionCapabilityFinding(
                CATALOG_PATH.as_posix(), f"schema_version must be {EXPECTED_SCHEMA_VERSION}"
            )
        )
    if payload.get("repository") != "lotus-core":
        findings.append(
            TransactionCapabilityFinding(CATALOG_PATH.as_posix(), "repository mismatch")
        )
    if payload.get("source_registry") != REGISTRY_PATH.as_posix():
        findings.append(
            TransactionCapabilityFinding(CATALOG_PATH.as_posix(), "source_registry mismatch")
        )
    if payload.get("guard_command") != GUARD_COMMAND:
        findings.append(
            TransactionCapabilityFinding(CATALOG_PATH.as_posix(), "guard_command mismatch")
        )
    _validate_transaction_types(
        findings=findings,
        entries=payload.get("transaction_types"),
        registry=registry,
    )
    _validate_product_lifecycles(
        findings=findings,
        entries=payload.get("product_lifecycles"),
        root=root,
        registry=registry,
    )
    _validate_documentation_surfaces(
        findings=findings,
        root=root,
        surfaces=payload.get("documentation_surfaces"),
    )
    return findings


def main() -> int:
    """Run the transaction capability catalog guard."""

    findings = find_transaction_capability_findings()
    if findings:
        print("transaction capability catalog guard failed:")
        for finding in findings:
            print(f"- {finding.location}: {finding.detail}")
        return 1
    print("transaction capability catalog guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
