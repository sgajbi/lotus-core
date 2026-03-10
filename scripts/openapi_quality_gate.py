"""Enforce OpenAPI quality across lotus-core API services."""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

# Ensure the repository root is importable when script is executed directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("LOTUS_TOOLING_QUIET", "1")
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


def _has_request_example(operation: dict) -> bool:
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return True
    content = request_body.get("content", {})
    if not isinstance(content, dict) or not content:
        return True
    json_media = [media for media_type, media in content.items() if "json" in media_type]
    if not json_media:
        return True
    return all(
        isinstance(media, dict) and ("example" in media or "examples" in media)
        for media in json_media
    )


def _has_parameter_examples(operation: dict) -> bool:
    parameters = operation.get("parameters", [])
    if not isinstance(parameters, list):
        return True
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if "example" in parameter or "examples" in parameter:
            continue
        return False
    return True


def _missing_success_response_examples(operation: dict) -> list[str]:
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return []
    missing: list[str] = []
    for code, response in responses.items():
        if not str(code).startswith("2"):
            continue
        if not isinstance(response, dict):
            continue
        content = response.get("content", {})
        if not isinstance(content, dict):
            continue
        for media_type, media in content.items():
            if "json" not in media_type:
                continue
            if not isinstance(media, dict):
                continue
            if "example" not in media and "examples" not in media:
                missing.append(str(code))
    return missing


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
                missing_response_examples = _missing_success_response_examples(operation)
                if missing_response_examples:
                    missing_docs.append(
                        (
                            method_upper,
                            path,
                            f"success response example ({', '.join(missing_response_examples)})",
                        )
                    )

            if not _has_request_example(operation):
                missing_docs.append((method_upper, path, "request example"))
            if not _has_parameter_examples(operation):
                missing_docs.append((method_upper, path, "parameter example"))

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
    from src.services.calculators.cashflow_calculator_service.app.web import (
        app as cashflow_calculator_web_app,
    )
    from src.services.calculators.cost_calculator_service.app.web import (
        app as cost_calculator_web_app,
    )
    from src.services.calculators.position_calculator.app.web import (
        app as position_calculator_web_app,
    )
    from src.services.calculators.position_valuation_calculator.app.web import (
        app as position_valuation_calculator_web_app,
    )
    from src.services.event_replay_service.app.main import app as event_replay_app
    from src.services.financial_reconciliation_service.app.main import (
        app as financial_reconciliation_app,
    )
    from src.services.ingestion_service.app.main import app as ingestion_app
    from src.services.persistence_service.app.web import app as persistence_web_app
    from src.services.pipeline_orchestrator_service.app.web import (
        app as pipeline_orchestrator_web_app,
    )
    from src.services.portfolio_aggregation_service.app.web import (
        app as portfolio_aggregation_web_app,
    )
    from src.services.query_control_plane_service.app.main import app as query_control_plane_app
    from src.services.query_service.app.main import app as query_app
    from src.services.timeseries_generator_service.app.web import (
        app as timeseries_generator_web_app,
    )
    from src.services.valuation_orchestrator_service.app.web import (
        app as valuation_orchestrator_web_app,
    )

    service_schemas = {
        "query_service": query_app.openapi(),
        "query_control_plane_service": query_control_plane_app.openapi(),
        "ingestion_service": ingestion_app.openapi(),
        "event_replay_service": event_replay_app.openapi(),
        "financial_reconciliation_service": financial_reconciliation_app.openapi(),
        "pipeline_orchestrator_service_web": pipeline_orchestrator_web_app.openapi(),
        "persistence_service_web": persistence_web_app.openapi(),
        "valuation_orchestrator_service_web": valuation_orchestrator_web_app.openapi(),
        "portfolio_aggregation_service_web": portfolio_aggregation_web_app.openapi(),
        "timeseries_generator_service_web": timeseries_generator_web_app.openapi(),
        "position_calculator_service_web": position_calculator_web_app.openapi(),
        "cost_calculator_service_web": cost_calculator_web_app.openapi(),
        "cashflow_calculator_service_web": cashflow_calculator_web_app.openapi(),
        "position_valuation_calculator_service_web": (
            position_valuation_calculator_web_app.openapi()
        ),
    }
    errors: list[str] = []
    for service_name, schema in service_schemas.items():
        errors.extend(evaluate_schema(schema, service_name=service_name))

    if errors:
        print("\n".join(errors))
        return 1

    print("OpenAPI quality gate passed for API services.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
