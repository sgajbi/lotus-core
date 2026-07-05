from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "docs" / "standards" / "verified-api-examples.v1.json"
ROUTE_REGISTRY_PATH = REPO_ROOT / "docs" / "standards" / "route-contract-family-registry.json"
REQUIRED_CATEGORIES = {
    "success",
    "validation_error",
    "auth_permission_denial",
    "not_found",
    "conflict_idempotency",
    "dependency_timeout",
    "degraded_source_data",
    "pagination_filtering_sorting",
}
PROBLEM_CATEGORIES = REQUIRED_CATEGORIES - {
    "success",
    "degraded_source_data",
    "pagination_filtering_sorting",
}
FORBIDDEN_SENSITIVE_TERMS = {
    "john",
    "jane",
    "@",
    "passport",
    "ssn",
    "nric",
    "account_number",
}


@dataclass(frozen=True, slots=True)
class ApiExampleFinding:
    path: str
    rule: str
    detail: str

    def as_text(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def find_api_example_catalog_findings(root: Path) -> list[ApiExampleFinding]:
    root = root.resolve()
    catalog_path = root / CATALOG_PATH.relative_to(REPO_ROOT)
    registry_path = root / ROUTE_REGISTRY_PATH.relative_to(REPO_ROOT)
    findings: list[ApiExampleFinding] = []
    if not catalog_path.exists():
        return [
            ApiExampleFinding(
                path=CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-api-example-catalog",
                detail="verified API example catalog is missing",
            )
        ]
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    examples = catalog.get("examples", [])
    example_by_id = {
        example.get("id"): example for example in examples if isinstance(example.get("id"), str)
    }
    route_keys = _route_keys(registry)

    _validate_required_categories(examples, findings)
    _validate_route_family_links(catalog, route_keys, example_by_id, findings)
    for example in examples:
        _validate_example(example, route_keys, findings)
    return findings


def _route_keys(registry: dict[str, Any]) -> dict[tuple[str, str], set[str]]:
    route_keys: dict[tuple[str, str], set[str]] = {}
    for service, families in registry.get("routes", {}).items():
        for family, routes in families.items():
            route_keys[(service, family)] = set(routes)
    return route_keys


def _validate_required_categories(
    examples: list[dict[str, Any]],
    findings: list[ApiExampleFinding],
) -> None:
    categories = {example.get("category") for example in examples}
    missing = REQUIRED_CATEGORIES - categories
    if missing:
        findings.append(
            ApiExampleFinding(
                path=CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-required-api-example-category",
                detail=", ".join(sorted(missing)),
            )
        )


def _validate_route_family_links(
    catalog: dict[str, Any],
    route_keys: dict[tuple[str, str], set[str]],
    example_by_id: dict[str, dict[str, Any]],
    findings: list[ApiExampleFinding],
) -> None:
    links = catalog.get("routeFamilyLinks", [])
    linked_families = {
        (link.get("service"), link.get("family")) for link in links if isinstance(link, dict)
    }
    missing_families = set(route_keys) - linked_families
    if missing_families:
        findings.append(
            ApiExampleFinding(
                path=CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
                rule="missing-route-family-example-link",
                detail=", ".join(
                    f"{service}/{family}" for service, family in sorted(missing_families)
                ),
            )
        )
    for link in links:
        service = link.get("service")
        family = link.get("family")
        if (service, family) not in route_keys:
            findings.append(
                ApiExampleFinding(
                    path=CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
                    rule="unknown-route-family-example-link",
                    detail=f"{service}/{family}",
                )
            )
        for example_id in link.get("exampleIds", []):
            if example_id not in example_by_id:
                findings.append(
                    ApiExampleFinding(
                        path=CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
                        rule="unknown-route-family-example-id",
                        detail=str(example_id),
                    )
                )


def _validate_example(
    example: dict[str, Any],
    route_keys: dict[tuple[str, str], set[str]],
    findings: list[ApiExampleFinding],
) -> None:
    example_id = str(example.get("id", "<missing-id>"))
    service = example.get("service")
    family = example.get("family")
    route_key = f"{example.get('method')} {example.get('path')}"
    if route_key not in route_keys.get((service, family), set()):
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="example-route-not-registered",
                detail=f"{service}/{family} {route_key}",
            )
        )
    if not example.get("sourceTests"):
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="missing-source-test-reference",
                detail="examples must be backed by implementation or contract tests",
            )
        )
    response_body = example.get("response", {}).get("body", {})
    if not response_body.get("correlation_id"):
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="missing-correlation-id",
                detail="example response must include correlation_id",
            )
        )
    category = example.get("category")
    if category in PROBLEM_CATEGORIES:
        for field in ("code", "message", "correlation_id", "details"):
            if field not in response_body:
                findings.append(
                    ApiExampleFinding(
                        path=example_id,
                        rule="missing-problem-field",
                        detail=f"{category} example must include {field}",
                    )
                )
    if category == "conflict_idempotency" and "idempotency_key" not in response_body:
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="missing-idempotency-conflict-field",
                detail="idempotency conflict examples must include idempotency_key",
            )
        )
    if category == "degraded_source_data" and not (
        response_body.get("data_quality") or response_body.get("supportability")
    ):
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="missing-degraded-source-metadata",
                detail="degraded examples must include data_quality or supportability metadata",
            )
        )
    if category == "pagination_filtering_sorting":
        if not example.get("request", {}).get("body", {}).get("limit"):
            findings.append(
                ApiExampleFinding(
                    path=example_id,
                    rule="missing-pagination-request",
                    detail="pagination examples must include a request limit",
                )
            )
        if not response_body.get("page", {}).get("next_page_token"):
            findings.append(
                ApiExampleFinding(
                    path=example_id,
                    rule="missing-pagination-response",
                    detail="pagination examples must include next_page_token",
                )
            )
    sensitivity = example.get("sensitivity", {})
    if sensitivity.get("syntheticOnly") is not True:
        findings.append(
            ApiExampleFinding(
                path=example_id,
                rule="missing-synthetic-only-claim",
                detail="examples must declare syntheticOnly=true",
            )
        )
    rendered = json.dumps(example, sort_keys=True).lower()
    for forbidden in FORBIDDEN_SENSITIVE_TERMS:
        if forbidden in rendered:
            findings.append(
                ApiExampleFinding(
                    path=example_id,
                    rule="sensitive-example-term",
                    detail=forbidden,
                )
            )


def main() -> int:
    findings = find_api_example_catalog_findings(REPO_ROOT)
    if findings:
        for finding in findings:
            print(finding.as_text())
        return 1
    print("API example catalog guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
