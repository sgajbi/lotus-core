"""Enforce OpenAPI quality across lotus-core API services."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Ensure the repository root is importable when script is executed directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ingestion_service uses absolute "app.*" imports.
INGESTION_SERVICE_ROOT = REPO_ROOT / "src" / "services" / "ingestion_service"
if str(INGESTION_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_SERVICE_ROOT))

LIBS_ROOT = REPO_ROOT / "src" / "libs"
for lib_dir in LIBS_ROOT.glob("*"):
    if not lib_dir.is_dir():
        continue
    for candidate in (lib_dir, lib_dir / "src"):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))

ALLOWED_METHODS = {"get", "post", "put", "patch", "delete"}


def _has_success_response(operation: dict) -> bool:
    responses = operation.get("responses", {})
    return any(code.startswith("2") for code in responses)


def _has_error_response(operation: dict) -> bool:
    responses = operation.get("responses", {})
    return any(
        code.startswith("4") or code.startswith("5") or code == "default" for code in responses
    )


def _is_ref_only(prop_schema: dict) -> bool:
    return set(prop_schema.keys()) == {"$ref"}


def evaluate_schema(schema: dict, service_name: str) -> list[str]:
    errors: list[str] = []
    missing_docs: list[tuple[str, str, str]] = []
    missing_fields: list[tuple[str, str, str]] = []
    operation_ids: list[str] = []

    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in ALLOWED_METHODS:
                continue

            method_upper = method.upper()
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)

            if not operation.get("summary"):
                missing_docs.append((method_upper, path, "summary"))
            if not operation.get("description"):
                missing_docs.append((method_upper, path, "description"))
            if not operation.get("tags"):
                missing_docs.append((method_upper, path, "tags"))

            if not operation.get("responses"):
                missing_docs.append((method_upper, path, "responses"))
            else:
                if not _has_success_response(operation):
                    missing_docs.append((method_upper, path, "2xx response"))
                if not _has_error_response(operation):
                    missing_docs.append((method_upper, path, "error response (4xx/5xx/default)"))

    schemas = schema.get("components", {}).get("schemas", {})
    for model_name, model_schema in schemas.items():
        properties = model_schema.get("properties", {})
        if not isinstance(properties, dict):
            continue
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            if _is_ref_only(prop_schema):
                continue
            if not prop_schema.get("description"):
                missing_fields.append((model_name, prop_name, "description"))
            if "example" not in prop_schema and "examples" not in prop_schema:
                missing_fields.append((model_name, prop_name, "example"))

    if missing_docs:
        errors.append(
            f"OpenAPI quality gate ({service_name}): missing endpoint "
            "documentation/response contract"
        )
        errors.extend(
            f"  - {method} {path}: missing {field_name}"
            for method, path, field_name in missing_docs
        )

    if missing_fields:
        errors.append(f"OpenAPI quality gate ({service_name}): missing schema field metadata")
        errors.extend(
            f"  - {model}.{field}: missing {field_name}"
            for model, field, field_name in missing_fields
        )

    op_id_counts = Counter(operation_ids)
    duplicate_operation_ids = sorted([op_id for op_id, count in op_id_counts.items() if count > 1])
    if duplicate_operation_ids:
        errors.append(f"OpenAPI quality gate ({service_name}): duplicate operationId values")
        errors.extend(f"  - {op_id}" for op_id in duplicate_operation_ids)

    return errors


def main() -> int:
    from src.services.ingestion_service.app.main import app as ingestion_app
    from src.services.query_service.app.main import app as query_app

    service_schemas = {
        "query_service": query_app.openapi(),
        "ingestion_service": ingestion_app.openapi(),
    }
    errors: list[str] = []
    for service_name, schema in service_schemas.items():
        errors.extend(evaluate_schema(schema, service_name=service_name))

    if errors:
        print("\n".join(errors))
        return 1

    print("OpenAPI quality gate passed for query_service and ingestion_service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
