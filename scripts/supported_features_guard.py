"""Validate supported-feature publication against implementation evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("contracts/supported-features/lotus-core-supported-features.v1.json")
DOMAIN_PRODUCTS_PATH = Path("contracts/domain-data-products/lotus-core-products.v1.json")
EXPECTED_SCHEMA_VERSION = "lotus-core-supported-features.v1"
ALLOWED_STATUSES = {
    "supported",
    "supported_with_fail_closed_dependencies",
    "producer_certified_downstream_owned",
    "fail_closed_external_dependency",
}
REQUIRED_CAPABILITY_FIELDS = (
    "id",
    "display_name",
    "owner",
    "status",
    "implementation_modules",
    "routes",
    "tests",
    "validation_evidence",
    "safe_demo_claims",
    "prohibited_claims",
    "limitations",
    "downstream_ownership_caveats",
)
REQUIRED_CLAIM_FIELDS = ("claim", "evidence_refs")
REQUIRED_PROHIBITED_CLAIM_FIELDS = ("claim", "owning_service_boundary", "evidence_refs")


@dataclass(frozen=True)
class SupportedFeatureFinding:
    location: str
    detail: str


def _load_json(relative_path: Path) -> Any:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _domain_product_refs() -> set[str]:
    payload = _load_json(DOMAIN_PRODUCTS_PATH)
    return {
        f"{product['product_name']}:{product['product_version']}"
        for product in payload.get("products", [])
    }


def _path_exists(reference: str) -> bool:
    return (REPO_ROOT / reference).exists()


def _looks_like_path(reference: str) -> bool:
    return "/" in reference or "\\" in reference or Path(reference).suffix != ""


def _reference_is_valid(reference: str) -> bool:
    if reference.startswith(("/", "make ", "python ", "output/")):
        return True
    if _looks_like_path(reference):
        return _path_exists(reference)
    return True


def _require_non_empty_list(
    *,
    findings: list[SupportedFeatureFinding],
    capability_id: str,
    field_name: str,
    capability: dict[str, Any],
) -> list[Any]:
    value = capability.get(field_name)
    if not isinstance(value, list) or not value:
        findings.append(
            SupportedFeatureFinding(capability_id, f"{field_name} must be a non-empty list")
        )
        return []
    return value


def _validate_claims(
    *,
    findings: list[SupportedFeatureFinding],
    capability_id: str,
    field_name: str,
    claims: list[Any],
    required_fields: tuple[str, ...],
) -> None:
    for index, claim in enumerate(claims):
        location = f"{capability_id}.{field_name}[{index}]"
        if not isinstance(claim, dict):
            findings.append(SupportedFeatureFinding(location, "claim entry must be an object"))
            continue
        for required_field in required_fields:
            value = claim.get(required_field)
            if not value:
                findings.append(SupportedFeatureFinding(location, f"missing {required_field}"))
        evidence_refs = claim.get("evidence_refs", [])
        if not isinstance(evidence_refs, list) or not evidence_refs:
            findings.append(
                SupportedFeatureFinding(location, "evidence_refs must be a non-empty list")
            )
            continue
        for reference in evidence_refs:
            if not isinstance(reference, str) or not _reference_is_valid(reference):
                findings.append(
                    SupportedFeatureFinding(location, f"invalid evidence reference {reference!r}")
                )


def _validate_capability(
    *,
    findings: list[SupportedFeatureFinding],
    capability: dict[str, Any],
    product_refs: set[str],
) -> None:
    capability_id = str(capability.get("id") or "<missing-id>")
    for field_name in REQUIRED_CAPABILITY_FIELDS:
        if field_name not in capability or capability[field_name] in (None, "", []):
            findings.append(SupportedFeatureFinding(capability_id, f"missing {field_name}"))

    status = capability.get("status")
    if status not in ALLOWED_STATUSES:
        findings.append(SupportedFeatureFinding(capability_id, f"unsupported status {status!r}"))

    if status and "fail_closed" in status:
        limitation_text = " ".join(capability.get("limitations", []))
        if "fail-closed" not in limitation_text:
            findings.append(
                SupportedFeatureFinding(
                    capability_id,
                    "fail-closed capability status must be reflected in limitations",
                )
            )

    for field_name in ("implementation_modules", "tests"):
        for reference in _require_non_empty_list(
            findings=findings,
            capability_id=capability_id,
            field_name=field_name,
            capability=capability,
        ):
            if not isinstance(reference, str) or not _path_exists(reference):
                findings.append(
                    SupportedFeatureFinding(
                        capability_id,
                        f"{field_name} reference does not exist: {reference!r}",
                    )
                )

    for route in _require_non_empty_list(
        findings=findings,
        capability_id=capability_id,
        field_name="routes",
        capability=capability,
    ):
        if not isinstance(route, str) or not route.startswith("/"):
            findings.append(
                SupportedFeatureFinding(capability_id, f"route must start with /: {route!r}")
            )

    for product_ref in capability.get("source_data_products", []):
        if product_ref not in product_refs:
            findings.append(
                SupportedFeatureFinding(
                    capability_id,
                    f"source_data_products reference not in domain product contract: {product_ref}",
                )
            )

    for reference in _require_non_empty_list(
        findings=findings,
        capability_id=capability_id,
        field_name="validation_evidence",
        capability=capability,
    ):
        if not isinstance(reference, str) or not _reference_is_valid(reference):
            findings.append(
                SupportedFeatureFinding(
                    capability_id,
                    f"validation evidence reference is invalid: {reference!r}",
                )
            )

    _validate_claims(
        findings=findings,
        capability_id=capability_id,
        field_name="safe_demo_claims",
        claims=capability.get("safe_demo_claims", []),
        required_fields=REQUIRED_CLAIM_FIELDS,
    )
    _validate_claims(
        findings=findings,
        capability_id=capability_id,
        field_name="prohibited_claims",
        claims=capability.get("prohibited_claims", []),
        required_fields=REQUIRED_PROHIBITED_CLAIM_FIELDS,
    )


def _validate_documentation_surfaces(
    *,
    findings: list[SupportedFeatureFinding],
    payload: dict[str, Any],
) -> None:
    capabilities = payload.get("capabilities", [])
    required_guard = payload.get("guard_command")
    for surface in payload.get("documentation_surfaces", []):
        surface_path = REPO_ROOT / surface
        if not surface_path.exists():
            findings.append(SupportedFeatureFinding(surface, "documentation surface is missing"))
            continue
        text = surface_path.read_text(encoding="utf-8")
        if MANIFEST_PATH.as_posix() not in text:
            findings.append(
                SupportedFeatureFinding(
                    surface,
                    f"missing canonical manifest reference {MANIFEST_PATH.as_posix()}",
                )
            )
        if required_guard and required_guard not in text:
            findings.append(
                SupportedFeatureFinding(surface, f"missing guard command {required_guard}")
            )
        for capability in capabilities:
            display_name = capability.get("display_name")
            if display_name and display_name not in text:
                findings.append(
                    SupportedFeatureFinding(
                        surface,
                        f"missing capability display name {display_name!r}",
                    )
                )

    docs_path = REPO_ROOT / "docs" / "supported-features.md"
    if docs_path.exists():
        docs_text = docs_path.read_text(encoding="utf-8")
        for capability in capabilities:
            status = capability.get("status")
            if status and status not in docs_text:
                findings.append(
                    SupportedFeatureFinding(
                        "docs/supported-features.md",
                        f"missing status {status!r} for {capability.get('id')}",
                    )
                )


def find_supported_feature_findings(root: Path = REPO_ROOT) -> list[SupportedFeatureFinding]:
    global REPO_ROOT
    original_root = REPO_ROOT
    REPO_ROOT = root
    try:
        findings: list[SupportedFeatureFinding] = []
        manifest = root / MANIFEST_PATH
        if not manifest.exists():
            return [
                SupportedFeatureFinding(
                    MANIFEST_PATH.as_posix(),
                    "supported-feature manifest is missing",
                )
            ]
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
            findings.append(
                SupportedFeatureFinding(
                    MANIFEST_PATH.as_posix(),
                    f"schema_version must be {EXPECTED_SCHEMA_VERSION}",
                )
            )
        if payload.get("repository") != "lotus-core":
            findings.append(
                SupportedFeatureFinding(MANIFEST_PATH.as_posix(), "repository must be lotus-core")
            )
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            findings.append(
                SupportedFeatureFinding(MANIFEST_PATH.as_posix(), "capabilities must be non-empty")
            )
            capabilities = []
        ids = [capability.get("id") for capability in capabilities if isinstance(capability, dict)]
        duplicate_ids = sorted(
            {capability_id for capability_id in ids if ids.count(capability_id) > 1}
        )
        for capability_id in duplicate_ids:
            findings.append(
                SupportedFeatureFinding(
                    MANIFEST_PATH.as_posix(), f"duplicate capability id {capability_id}"
                )
            )
        product_refs = _domain_product_refs()
        for capability in capabilities:
            if not isinstance(capability, dict):
                findings.append(
                    SupportedFeatureFinding(
                        MANIFEST_PATH.as_posix(), "capability must be an object"
                    )
                )
                continue
            _validate_capability(
                findings=findings,
                capability=capability,
                product_refs=product_refs,
            )
        _validate_documentation_surfaces(findings=findings, payload=payload)
        return findings
    finally:
        REPO_ROOT = original_root


def main() -> int:
    findings = find_supported_feature_findings(REPO_ROOT)
    if findings:
        for finding in findings:
            print(f"{finding.location}: {finding.detail}")
        raise SystemExit(1)
    print("Supported features guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
