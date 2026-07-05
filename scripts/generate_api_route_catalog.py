"""Generate and validate the implementation-backed API route catalog."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("LOTUS_TOOLING_QUIET", "1")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CATALOG_PATH = REPO_ROOT / "docs" / "standards" / "api-route-catalog.v1.json"
ROUTE_REGISTRY_PATH = REPO_ROOT / "docs" / "standards" / "route-contract-family-registry.json"
SCHEMA_VERSION = "lotus-core.api-route-catalog.v1"
GUARD_COMMAND = "python scripts/generate_api_route_catalog.py --check"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

SHARED_OPERATIONAL_PATHS = {
    "/health/live",
    "/health/ready",
    "/metrics",
    "/openapi.json",
    "/version",
}
FAMILY_DOWNSTREAM_CONSUMERS = {
    "Analytics Input": ["lotus-performance", "lotus-risk", "lotus-workbench"],
    "Control Execution": ["lotus-workbench", "operations"],
    "Control-Plane And Policy": ["lotus-gateway", "lotus-workbench", "operations"],
    "Operational Read": ["lotus-gateway", "lotus-workbench", "lotus-report"],
    "Snapshot And Simulation": ["lotus-advise", "lotus-manage", "lotus-workbench"],
    "Write Ingress": ["source-adapters", "operations"],
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def route_family_index(registry: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for service_app, family_map in registry.get("routes", {}).items():
        if not isinstance(family_map, dict):
            continue
        for family, route_keys in family_map.items():
            if not isinstance(route_keys, list):
                continue
            for route_key in route_keys:
                index[f"{service_app} {route_key}"] = str(family)
    return index


def generate_catalog_payload(
    openapi_by_service: dict[str, dict[str, Any]],
    route_registry: dict[str, Any],
) -> dict[str, Any]:
    family_index = route_family_index(route_registry)
    entries = [
        _operation_catalog_entry(
            service_app=service_app,
            method=method.upper(),
            path=path,
            operation=operation,
            family_index=family_index,
        )
        for service_app, schema in sorted(openapi_by_service.items())
        for path, methods in sorted(schema.get("paths", {}).items())
        if isinstance(methods, dict)
        for method, operation in sorted(methods.items())
        if method.lower() in HTTP_METHODS and isinstance(operation, dict)
    ]
    entries.sort(key=lambda item: (item["service_app"], item["path"], item["method"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": "lotus-core",
        "generated_from": [
            "FastAPI OpenAPI output",
            "docs/standards/route-contract-family-registry.json",
        ],
        "guard_command": GUARD_COMMAND,
        "description": (
            "Implementation-backed API route catalog generated from OpenAPI and enriched with "
            "RFC-0082/RFC-0083 route-family governance metadata."
        ),
        "entries": entries,
    }


def _operation_catalog_entry(
    *,
    service_app: str,
    method: str,
    path: str,
    operation: dict[str, Any],
    family_index: dict[str, str],
) -> dict[str, Any]:
    route_key = f"{method} {path}"
    route_family = _route_family(
        service_app=service_app,
        method=method,
        path=path,
        family_index=family_index,
    )
    return {
        "service_app": service_app,
        "method": method,
        "path": path,
        "route_key": route_key,
        "operation_id": operation.get("operationId"),
        "summary": operation.get("summary"),
        "tags": operation.get("tags", []),
        "route_family": route_family,
        "api_version": _api_version(path),
        "api_status": "deprecated" if operation.get("deprecated") else "active",
        "owner": service_app,
        "auth_requirement": _auth_requirement(operation, route_family, path),
        "audit_requirement": _audit_requirement(route_family, method),
        "request_schema": _request_schema(operation),
        "response_schemas": _response_schemas(operation, success_only=True),
        "error_models": _response_schemas(operation, success_only=False),
        "pagination": _parameter_semantics(operation, "pagination"),
        "filtering": _parameter_semantics(operation, "filtering"),
        "sorting": _parameter_semantics(operation, "sorting"),
        "idempotency_behavior": _idempotency_behavior(operation, method, route_family),
        "downstream_consumers": FAMILY_DOWNSTREAM_CONSUMERS.get(route_family, []),
        "deprecated_alias_metadata": {
            "is_deprecated": bool(operation.get("deprecated")),
            "sunset": operation.get("x-sunset-date"),
            "compatibility": operation.get("x-lotus-compatibility", "not_applicable"),
        },
    }


def _shared_route_family(path: str) -> str:
    if path in SHARED_OPERATIONAL_PATHS:
        return "Shared Operational"
    return "Unclassified"


def _route_family(*, service_app: str, method: str, path: str, family_index: dict[str, str]) -> str:
    candidate_paths = [path]
    if path != "/" and path.endswith("/"):
        candidate_paths.append(path.rstrip("/"))
    for candidate_path in candidate_paths:
        route_key = f"{method} {candidate_path}"
        route_family = family_index.get(f"{service_app} {route_key}")
        if route_family:
            return route_family
    return _shared_route_family(path)


def _api_version(path: str) -> str:
    first_segment = path.strip("/").split("/", 1)[0]
    if first_segment.startswith("v") and first_segment[1:].isdigit():
        return first_segment
    return "unversioned-current"


def _auth_requirement(operation: dict[str, Any], route_family: str, path: str) -> str:
    if operation.get("security"):
        return "openapi-security-declared"
    if path == "/metrics":
        return "metrics-token-when-configured"
    if route_family in {"Write Ingress", "Control Execution", "Control-Plane And Policy"}:
        return "governed-enterprise-readiness"
    return "not-declared-in-openapi"


def _audit_requirement(route_family: str, method: str) -> str:
    if route_family in {"Write Ingress", "Control Execution", "Control-Plane And Policy"}:
        return "audit-required"
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return "mutation-audit-required"
    return "read-audit-where-policy-requires"


def _request_schema(operation: dict[str, Any]) -> str | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content")
    if not isinstance(content, dict):
        return None
    for media_type in ("application/json", "multipart/form-data"):
        media = content.get(media_type)
        if isinstance(media, dict):
            return _schema_name(media.get("schema"))
    return None


def _response_schemas(operation: dict[str, Any], *, success_only: bool) -> list[dict[str, str]]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    rows: list[dict[str, str]] = []
    for status_code, response in sorted(responses.items(), key=lambda item: str(item[0])):
        code = str(status_code)
        is_success = code.startswith("2")
        if is_success != success_only:
            continue
        if not isinstance(response, dict):
            continue
        schema_name = _first_response_schema(response)
        rows.append(
            {
                "status_code": code,
                "schema": schema_name or "none",
                "description": str(response.get("description", "")),
            }
        )
    return rows


def _first_response_schema(response: dict[str, Any]) -> str | None:
    content = response.get("content")
    if not isinstance(content, dict):
        return None
    for media in content.values():
        if isinstance(media, dict):
            schema_name = _schema_name(media.get("schema"))
            if schema_name:
                return schema_name
    return None


def _schema_name(schema: object) -> str | None:
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    title = schema.get("title")
    if isinstance(title, str):
        return title
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return schema_type
    return None


def _parameter_semantics(operation: dict[str, Any], semantic: str) -> list[str]:
    names = [
        str(parameter.get("name"))
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str)
    ]
    if semantic == "pagination":
        terms = ("cursor", "limit", "page", "offset")
    elif semantic == "filtering":
        terms = ("filter", "status", "from", "to", "as_of", "portfolio_id", "security_id")
    else:
        terms = ("sort", "order")
    return [name for name in names if any(term in name for term in terms)]


def _idempotency_behavior(operation: dict[str, Any], method: str, route_family: str) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            operation.get("summary"),
            operation.get("description"),
            operation.get("operationId"),
        )
    ).lower()
    if "idempotency" in text:
        return "idempotency-key-aware"
    if route_family == "Write Ingress" and method == "POST":
        return "ingestion-job-idempotency-supported-where-header-present"
    if method in {"GET", "HEAD"}:
        return "safe-read"
    return "not-declared"


def load_current_openapi() -> dict[str, dict[str, Any]]:
    from scripts.openapi_quality_gate import service_schemas

    return service_schemas()


def validate_catalog(payload: dict[str, Any], generated: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"catalog schema_version must be {SCHEMA_VERSION!r}")
    if payload.get("repository") != "lotus-core":
        errors.append("catalog repository must be 'lotus-core'")
    if payload.get("guard_command") != GUARD_COMMAND:
        errors.append(f"catalog guard_command must be {GUARD_COMMAND!r}")
    actual_keys = _entry_keys(payload)
    generated_keys = _entry_keys(generated)
    missing = sorted(generated_keys - actual_keys)
    stale = sorted(actual_keys - generated_keys)
    if missing:
        errors.append("API route catalog is missing implemented routes: " + ", ".join(missing))
    if stale:
        errors.append("API route catalog contains stale routes: " + ", ".join(stale))
    if payload != generated:
        errors.append(
            "API route catalog is not current; run python scripts/generate_api_route_catalog.py"
        )
    return errors


def _entry_keys(payload: dict[str, Any]) -> set[str]:
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return set()
    return {
        f"{entry.get('service_app')} {entry.get('method')} {entry.get('path')}"
        for entry in entries
        if isinstance(entry, dict)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    parser.add_argument(
        "--check", action="store_true", help="Fail when the tracked catalog drifts."
    )
    args = parser.parse_args()

    generated = generate_catalog_payload(load_current_openapi(), load_json(ROUTE_REGISTRY_PATH))
    if args.check:
        errors = validate_catalog(load_json(args.output), generated)
        if errors:
            print("API route catalog guard failed:")
            for error in errors:
                print(f"- {error}")
            return 1
        print("API route catalog guard passed.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote API route catalog: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
