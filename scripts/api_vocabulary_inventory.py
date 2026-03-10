"""Generate and validate lotus-core API vocabulary inventory."""

from __future__ import annotations

import json
import os
import re
import sys
from argparse import ArgumentParser
from datetime import UTC, datetime
from numbers import Real
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("LOTUS_TOOLING_QUIET", "1")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
LEGACY_TERM_MAP: dict[str, str] = {}
BANNED_NAME_PREFIXES = ("query_", "ingestion_", "dto_", "db_")
EXAMPLE_BY_KEY = {
    "amount": 125000.5,
    "asset_class": "EQUITY",
    "attempt_count": 1,
    "baseline_as_of": "2026-02-27",
    "cashflow": 3200.0,
    "cost_basis_local": 95000.0,
    "cost_basis_method": "FIFO",
    "country_of_risk": "US",
    "created_by": "lotus-manage",
    "current_epoch": 42,
    "description": "Portfolio-level metric description.",
    "epoch": 42,
    "failure_reason": "missing_market_price",
    "id": "ITEM_001",
    "income": 1450.25,
    "instrument_details": {"security_id": "AAPL"},
    "instrument_name": "Apple Inc.",
    "isin": "US0378331005",
    "key": "portfolio_state",
    "label": "Global Equity Portfolio",
    "message": "Operation completed successfully.",
    "metadata": {"source": "lotus-core"},
    "net_cost": 98000.0,
    "net_cost_local": 98000.0,
    "objective": "CAPITAL_APPRECIATION",
    "owner_service": "lotus-core",
    "policy_source": "tenant-default-policy",
    "positions_baseline": [{"security_id": "SEC_AAPL_US", "quantity": "100.0000000000"}],
    "positions_projected": [{"security_id": "SEC_AAPL_US", "quantity": "120.0000000000"}],
    "positions_delta": [{"security_id": "SEC_AAPL_US", "delta_quantity": "20.0000000000"}],
    "portfolio_type": "DISCRETIONARY",
    "rate": 1.2345,
    "rating": "A",
    "realized_gain_loss": 525.75,
    "realized_gain_loss_local": 525.75,
    "risk_exposure": "MODERATE",
    "sector": "TECHNOLOGY",
    "transaction_fx_rate": 1.1032,
    "transaction_type": "BUY",
    "valuation": 125000.5,
    "valuation_context": {
        "portfolio_currency": "EUR",
        "reporting_currency": "USD",
        "position_basis": "market_value_base",
        "weight_basis": "total_market_value_base",
    },
    "sections": [
        "positions_baseline",
        "positions_projected",
        "positions_delta",
        "portfolio_totals",
        "instrument_enrichment",
    ],
    "asset_type": "EQUITY",
    "class": "EQUITY",
    "type": "STANDARD",
    "name": "Global Balanced Portfolio",
}


def _is_placeholder_example(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().upper()
    return normalized.endswith("_VALUE") or normalized in {"STANDARD", "EXAMPLE_VALUE"}


def _to_snake_case(value: str) -> str:
    transformed = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    transformed = transformed.replace("-", "_").replace(" ", "_").replace(".", "_")
    return transformed.lower()


def _semantic_id(name: str) -> str:
    return f"lotus.{_canonical_name(name)}"


def _canonical_name(name: str) -> str:
    normalized = _to_snake_case(name)
    return LEGACY_TERM_MAP.get(normalized, normalized)


def _fallback_description(name: str, schema: dict[str, Any], *, context: str) -> str:
    key = _canonical_name(_leaf_name(name))
    readable = key.replace("_", " ")
    schema_format = schema.get("format")
    if key.endswith("_id"):
        entity = key[: -len("_id")].replace("_", " ")
        return f"Unique {entity} identifier."
    if schema_format == "date":
        return f"Business date for {readable}."
    if schema_format == "date-time":
        return f"Timestamp for {readable}."
    if "currency" in key:
        return f"ISO currency code for {readable}."
    if any(term in key for term in ("amount", "value", "pnl")):
        return f"Monetary value for {readable}."
    if "quantity" in key:
        return f"Quantity for {readable}."
    if any(term in key for term in ("price", "rate")):
        return f"Rate/price value for {readable}."
    if "status" in key:
        return f"Status for {readable}."
    return f"Canonical {readable} value used in {context.lower()}."


def _fallback_example(name: str, schema: dict[str, Any]) -> Any:
    key = _canonical_name(_leaf_name(name))
    if key in EXAMPLE_BY_KEY:
        return EXAMPLE_BY_KEY[key]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    schema_type = schema.get("type")
    schema_format = schema.get("format")
    if schema_type == "boolean":
        return True
    if schema_type == "integer":
        return 10
    if schema_type == "number":
        if any(term in key for term in ("amount", "value", "pnl")):
            return 125000.5
        if any(term in key for term in ("price", "rate")):
            return 1.2345
        return 10.5
    if schema_type == "array":
        item_schema = schema.get("items", {})
        if isinstance(item_schema, dict):
            return [_fallback_example(f"{name}_item", item_schema)]
        return ["example_value"]
    if schema_type == "object":
        if key in {"instrument_details", "metadata"}:
            return {"source": "lotus-core", "as_of_date": "2026-02-27"}
        return {"id": "OBJ_001"}
    if schema_format == "date":
        return "2026-02-27"
    if schema_format == "date-time":
        return "2026-02-27T10:30:00Z"
    if key.endswith("_id"):
        entity = key[: -len("_id")]
        return f"{entity.upper()}_001"
    if "asset_class" in key:
        return "EQUITY"
    if "portfolio_type" in key:
        return "DISCRETIONARY"
    if key in {"risk_exposure", "risk_profile"}:
        return "MODERATE"
    if key in {"objective"}:
        return "CAPITAL_APPRECIATION"
    if key in {"sector"}:
        return "TECHNOLOGY"
    if key in {"country_of_risk"}:
        return "US"
    if key in {"instrument_name", "name"}:
        return "Apple Inc."
    if key in {"description"}:
        return "Core portfolio attribute used for analytics and reporting."
    if key in {"message"}:
        return "Operation completed successfully."
    if "currency" in key:
        return "USD"
    if "status" in key:
        return "ACTIVE"
    if "date" in key:
        return "2026-02-27"
    if "time" in key:
        return "2026-02-27T10:30:00Z"
    return "STANDARD"


def _safe_json(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, str | int | Real) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    return str(value)


def _infer_type_from_example(example: Any) -> str:
    if isinstance(example, bool):
        return "boolean"
    if isinstance(example, int):
        return "integer"
    if isinstance(example, Real):
        return "number"
    if isinstance(example, list):
        return "array"
    if isinstance(example, dict):
        return "object"
    return "string"


def _preferred_type(observed_types: set[str], example: Any) -> str:
    priority = ["string", "integer", "number", "boolean", "array", "object"]
    normalized = {str(t).lower() for t in observed_types if t}
    for candidate in priority:
        if candidate in normalized:
            return candidate
    inferred = _infer_type_from_example(example)
    if inferred == "string" and "object" in normalized and len(normalized) == 1:
        return "string"
    return inferred


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in schema:
        return schema
    ref = schema["$ref"]
    ref_name = ref.rsplit("/", 1)[-1]
    return components.get("schemas", {}).get(ref_name, {})


def _schema_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    return str(schema.get("type", "object"))


def _extract_fields(
    schema: dict[str, Any],
    components: dict[str, Any],
    prefix: str = "",
    location: str = "body",
) -> list[dict[str, Any]]:
    resolved = _resolve_schema(schema, components)
    properties = resolved.get("properties", {})
    required = set(resolved.get("required", []))
    if not isinstance(properties, dict):
        return []

    fields: list[dict[str, Any]] = []
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        prop_resolved = _resolve_schema(prop_schema, components)
        # Keep wrapper metadata (description/example/enum/etc.) when property is a $ref/anyOf.
        # Wrapper fields are often where OpenAPI carries usage-specific examples.
        prop_effective = dict(prop_resolved)
        for key in ("description", "example", "examples", "enum", "format", "type", "items"):
            if key in prop_schema:
                prop_effective[key] = prop_schema[key]
        field_name = f"{prefix}.{prop_name}" if prefix else prop_name
        entry = {
            "name": field_name,
            "location": location,
            "type": _schema_type(prop_schema),
            "required": prop_name in required,
            "description": prop_effective.get("description")
            or _fallback_description(field_name, prop_effective, context="API body"),
            "example": _safe_json(
                prop_effective.get("example")
                if prop_effective.get("example") is not None
                else (
                    prop_effective.get("examples", [None])[0]
                    if isinstance(prop_effective.get("examples"), list)
                    and prop_effective.get("examples")
                    else _fallback_example(field_name, prop_effective)
                )
            ),
            "canonicalTerm": _canonical_name(prop_name),
            "semanticId": _semantic_id(prop_name),
        }
        if prop_effective.get("enum"):
            entry["enumValues"] = prop_effective["enum"]
        if prop_effective.get("format"):
            entry["format"] = prop_effective["format"]
        fields.append(entry)

        nested_type = prop_effective.get("type")
        if nested_type == "object" or "$ref" in prop_schema:
            fields.extend(
                _extract_fields(
                    prop_schema,
                    components=components,
                    prefix=field_name,
                    location=location,
                )
            )
        elif nested_type == "array":
            item_schema = prop_effective.get("items", {})
            if isinstance(item_schema, dict):
                fields.extend(
                    _extract_fields(
                        item_schema,
                        components=components,
                        prefix=f"{field_name}[]",
                        location=location,
                    )
                )
    return fields


def _extract_response_fields(
    operation: dict[str, Any],
    components: dict[str, Any],
) -> tuple[int | None, str | None, list[dict[str, Any]]]:
    responses = operation.get("responses", {})
    success_codes = sorted([code for code in responses if code.startswith("2")])
    if not success_codes:
        return None, None, []
    code = success_codes[0]
    response = responses[code]
    content = response.get("content", {})
    json_content = content.get("application/json")
    if not isinstance(json_content, dict):
        return int(code), None, []
    schema = json_content.get("schema", {})
    if not isinstance(schema, dict):
        return int(code), None, []
    model_name = _schema_type(schema)
    fields = _extract_fields(schema, components=components, prefix="", location="body")
    return int(code), model_name, fields


def _extract_request_fields(
    operation: dict[str, Any],
    components: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    request_fields: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []

    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        schema = parameter.get("schema", {})
        if not isinstance(schema, dict):
            schema = {}
        name = parameter.get("name", "")
        entry = {
            "name": name,
            "location": parameter.get("in", "query"),
            "type": _schema_type(schema),
            "required": bool(parameter.get("required", False)),
            "description": parameter.get("description")
            or schema.get("description")
            or _fallback_description(name, schema, context="Request parameter"),
            "example": _safe_json(
                parameter.get("example")
                if parameter.get("example") is not None
                else (
                    schema.get("example")
                    if schema.get("example") is not None
                    else _fallback_example(name, schema)
                )
            ),
            "canonicalTerm": _canonical_name(name),
            "semanticId": _semantic_id(name),
        }
        if schema.get("enum"):
            entry["enumValues"] = schema["enum"]
        request_fields.append(entry)

        controls.append(
            {
                "name": name,
                "kind": "request_option",
                "location": parameter.get("in", "query"),
                "type": _schema_type(schema),
                "required": bool(parameter.get("required", False)),
                "default": _safe_json(schema.get("default", "")),
                "allowedValues": _safe_json(schema.get("enum", [])),
                "description": entry["description"],
                "example": entry["example"],
                "behaviorImpact": (
                    f"Affects {operation.get('operationId', 'operation')} request behavior."
                ),
                "exposure": "consumer_visible",
                "canonicalTerm": entry["canonicalTerm"],
                "semanticId": entry["semanticId"],
            }
        )

    request_body = operation.get("requestBody", {})
    if isinstance(request_body, dict):
        content = request_body.get("content", {})
        json_content = content.get("application/json")
        if isinstance(json_content, dict):
            schema = json_content.get("schema", {})
            if isinstance(schema, dict):
                request_fields.extend(
                    _extract_fields(schema, components=components, prefix="", location="body")
                )
    return request_fields, controls


def _derive_domain(path: str, tags: list[str]) -> str:
    if tags:
        return _to_snake_case(tags[0])
    segment = path.strip("/").split("/", 1)[0] if path.strip("/") else "root"
    return _to_snake_case(segment)


def _extract_service_inventory(
    service_name: str,
    schema: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    endpoints: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    components = schema.get("components", {})

    for path, methods in schema.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.lower() not in ALLOWED_METHODS or not isinstance(operation, dict):
                continue

            request_fields, operation_controls = _extract_request_fields(operation, components)
            status_code, response_model, response_fields = _extract_response_fields(
                operation, components
            )

            endpoint = {
                "operationId": operation.get("operationId", f"{method}_{path}"),
                "method": method.upper(),
                "path": path,
                "domain": _derive_domain(path, operation.get("tags", [])),
                "serviceGroup": "query" if "query" in service_name else "ingestion",
                "tags": operation.get("tags", []),
                "summary": operation.get("summary", ""),
                "description": operation.get("description", ""),
                "naming": {
                    "boundedContext": _derive_domain(path, operation.get("tags", [])),
                    "canonicalTerms": sorted(
                        {field["canonicalTerm"] for field in request_fields + response_fields}
                    ),
                },
                "request": {"fields": request_fields},
                "response": {
                    "httpStatus": status_code,
                    "model": response_model,
                    "fields": response_fields,
                },
            }
            endpoints.append(endpoint)
            controls.extend(operation_controls)

    return endpoints, controls


def _leaf_name(field_name: str) -> str:
    normalized = field_name.replace("[]", "")
    if "." in normalized:
        return normalized.split(".")[-1]
    return normalized


def _build_attribute_catalog(
    endpoints: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    by_semantic_id: dict[str, dict[str, Any]] = {}
    semantic_aliases: dict[str, set[str]] = {}
    semantic_locations: dict[str, set[str]] = {}
    semantic_types: dict[str, set[str]] = {}

    for endpoint in endpoints:
        fields = endpoint.get("request", {}).get("fields", []) + endpoint.get("response", {}).get(
            "fields", []
        )
        for field in fields:
            semantic_id = field.get("semanticId")
            if not semantic_id:
                continue
            alias = _leaf_name(str(field.get("name", "")))
            semantic_aliases.setdefault(semantic_id, set()).add(alias)
            semantic_locations.setdefault(semantic_id, set()).add(
                str(field.get("location", "body"))
            )
            semantic_types.setdefault(semantic_id, set()).add(str(field.get("type", "object")))

            existing = by_semantic_id.get(semantic_id)
            if existing is None:
                candidate_example = field.get("example", "")
                if candidate_example in ("", None) or _is_placeholder_example(candidate_example):
                    candidate_example = _fallback_example(
                        alias, {"type": field.get("type", "string")}
                    )
                by_semantic_id[semantic_id] = {
                    "semanticId": semantic_id,
                    "canonicalTerm": field.get("canonicalTerm", _canonical_name(alias)),
                    "preferredName": _canonical_name(alias),
                    "description": field.get("description", "")
                    or _fallback_description(
                        alias, {"type": field.get("type", "string")}, context="API"
                    ),
                    "example": candidate_example,
                }
            else:
                if not existing.get("description") and field.get("description"):
                    existing["description"] = field["description"]
                if existing.get("example", "") in ("", None) and field.get("example", "") != "":
                    existing["example"] = field["example"]
                if _is_placeholder_example(existing.get("example")):
                    existing["example"] = _fallback_example(
                        alias, {"type": field.get("type", "string")}
                    )

    catalog: list[dict[str, Any]] = []
    semantic_drift: list[str] = []
    for semantic_id, base in sorted(by_semantic_id.items()):
        aliases = sorted([alias for alias in semantic_aliases.get(semantic_id, set()) if alias])
        observed_types = semantic_types.get(semantic_id, {"object"})
        base["type"] = _preferred_type(observed_types, base.get("example"))
        base["locations"] = sorted(semantic_locations.get(semantic_id, {"body"}))
        base["observedTypes"] = sorted(observed_types)
        catalog.append(base)
        normalized_names = sorted({_to_snake_case(alias) for alias in aliases})
        if len(normalized_names) > 1:
            semantic_drift.append(
                "semantic naming drift for "
                f"{semantic_id}: multiple canonical names {normalized_names}"
            )

    return catalog, semantic_drift


def _link_endpoint_fields_to_catalog(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for endpoint in endpoints:
        transformed = dict(endpoint)
        for section in ("request", "response"):
            section_obj = dict(transformed.get(section, {}))
            fields = section_obj.get("fields", [])
            section_obj["fields"] = [
                {
                    "name": field.get("name"),
                    "location": field.get("location", "body"),
                    "required": bool(field.get("required", False)),
                    "type": field.get("type", "object"),
                    "semanticId": field.get("semanticId"),
                    "attributeRef": field.get("semanticId"),
                }
                for field in fields
            ]
            transformed[section] = section_obj
        linked.append(transformed)
    return linked


def _default_server_side_controls() -> list[dict[str, Any]]:
    return [
        {
            "name": "LOTUS_CORE_CAP_SUPPORT_APIS_ENABLED",
            "kind": "feature_toggle",
            "default": True,
            "description": "Toggles support overview capability exposure.",
            "affects": ["lotus_core.support.overview_api"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_cap_support_apis_enabled",
            "semanticId": "lotus.lotus_core_cap_support_apis_enabled",
        },
        {
            "name": "LOTUS_CORE_CAP_LINEAGE_APIS_ENABLED",
            "kind": "feature_toggle",
            "default": True,
            "description": "Toggles lineage capability exposure.",
            "affects": ["lotus_core.support.lineage_api"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_cap_lineage_apis_enabled",
            "semanticId": "lotus.lotus_core_cap_lineage_apis_enabled",
        },
        {
            "name": "LOTUS_CORE_CAP_UPLOAD_APIS_ENABLED",
            "kind": "feature_toggle",
            "default": True,
            "description": "Toggles bulk upload capability exposure.",
            "affects": ["lotus_core.ingestion.bulk_upload"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_cap_upload_apis_enabled",
            "semanticId": "lotus.lotus_core_cap_upload_apis_enabled",
        },
        {
            "name": "LOTUS_CORE_CAP_SIMULATION_ENABLED",
            "kind": "feature_toggle",
            "default": True,
            "description": "Toggles simulation capability exposure.",
            "affects": ["lotus_core.simulation.what_if"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_cap_simulation_enabled",
            "semanticId": "lotus.lotus_core_cap_simulation_enabled",
        },
        {
            "name": "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON",
            "kind": "service_policy",
            "default": "{}",
            "description": "Tenant-level capability and workflow override policy.",
            "affects": ["/integration/capabilities"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_capability_tenant_overrides_json",
            "semanticId": "lotus.lotus_core_capability_tenant_overrides_json",
        },
        {
            "name": "LOTUS_CORE_POLICY_VERSION",
            "kind": "service_policy",
            "default": "tenant-default-v1",
            "description": "Policy version surfaced in capabilities and policy metadata.",
            "affects": ["policy_version", "policy_provenance.policy_version"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_policy_version",
            "semanticId": "lotus.lotus_core_policy_version",
        },
        {
            "name": "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
            "kind": "service_policy",
            "default": "{}",
            "description": "Integration policy controlling allowed sections and strict mode.",
            "affects": ["/integration/policy/effective", "allowed_sections", "warnings"],
            "exposure": "server_side",
            "canonicalTerm": "lotus_core_integration_snapshot_policy_json",
            "semanticId": "lotus.lotus_core_integration_snapshot_policy_json",
        },
    ]


def generate_inventory() -> dict[str, Any]:
    from src.services.ingestion_service.app.main import app as ingestion_app
    from src.services.query_service.app.main import app as query_app

    query_schema = query_app.openapi()
    ingestion_schema = ingestion_app.openapi()

    query_endpoints, query_controls = _extract_service_inventory("query_service", query_schema)
    ingestion_endpoints, ingestion_controls = _extract_service_inventory(
        "ingestion_service", ingestion_schema
    )

    endpoints = query_endpoints + ingestion_endpoints
    attribute_catalog, _semantic_drift = _build_attribute_catalog(endpoints)
    controls = query_controls + ingestion_controls + _default_server_side_controls()
    linked_endpoints = _link_endpoint_fields_to_catalog(endpoints)

    return {
        "specVersion": "1.0.0",
        "application": "lotus-core",
        "sourceOpenApi": [
            {
                "service": "query_service",
                "version": query_schema.get("info", {}).get("version", ""),
                "openApiVersion": query_schema.get("openapi", ""),
            },
            {
                "service": "ingestion_service",
                "version": ingestion_schema.get("info", {}).get("version", ""),
                "openApiVersion": ingestion_schema.get("openapi", ""),
            },
        ],
        "generatedAt": datetime.now(UTC).isoformat(),
        "attributeCatalog": attribute_catalog,
        "controlsCatalog": controls,
        "endpoints": linked_endpoints,
    }


def validate_inventory(inventory: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if inventory.get("application") != "lotus-core":
        errors.append("inventory.application must be 'lotus-core'")

    endpoints = inventory.get("endpoints", [])
    if not isinstance(endpoints, list) or not endpoints:
        errors.append("inventory.endpoints must be a non-empty list")

    attributes = inventory.get("attributeCatalog", [])
    if not isinstance(attributes, list) or not attributes:
        errors.append("inventory.attributeCatalog must be a non-empty list")

    attribute_ids: set[str] = set()
    for attribute in attributes:
        semantic_id = attribute.get("semanticId")
        if not semantic_id:
            errors.append("attribute missing semanticId")
            continue
        if semantic_id in attribute_ids:
            errors.append(f"duplicate attribute semanticId found: {semantic_id}")
        attribute_ids.add(semantic_id)
        for key in ("canonicalTerm", "preferredName", "description", "example", "type"):
            value = attribute.get(key)
            if value in ("", None):
                errors.append(f"attribute '{semantic_id}' missing {key}")
        if str(attribute.get("type")) not in {
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
        }:
            errors.append(
                f"attribute '{semantic_id}' has unsupported type '{attribute.get('type')}'"
            )
        canonical_term = str(attribute.get("canonicalTerm", ""))
        preferred_name = str(attribute.get("preferredName", ""))
        if not re.fullmatch(r"[a-z][a-z0-9_]*", canonical_term):
            errors.append(f"attribute '{semantic_id}' has non-canonical term '{canonical_term}'")
        if canonical_term != preferred_name:
            errors.append(f"attribute '{semantic_id}' preferredName must match canonicalTerm")
        if canonical_term in LEGACY_TERM_MAP:
            errors.append(f"attribute '{semantic_id}' uses legacy term '{canonical_term}'")
        if any(canonical_term.startswith(prefix) for prefix in BANNED_NAME_PREFIXES):
            errors.append(
                f"attribute '{semantic_id}' uses implementation-specific "
                f"prefix in '{canonical_term}'"
            )
        description = str(attribute.get("description", "")).strip()
        if len(description) < 12:
            errors.append(f"attribute '{semantic_id}' description is too short for WM standard")
        example_value = str(attribute.get("example", "")).strip().lower()
        if example_value in {"example_value", "sample_value", "value"}:
            errors.append(f"attribute '{semantic_id}' example is generic and not self-explanatory")

    for endpoint in endpoints:
        for key in ("operationId", "method", "path", "summary", "description"):
            if not endpoint.get(key):
                errors.append(f"endpoint missing required key '{key}': {endpoint.get('path')}")

        request_fields = endpoint.get("request", {}).get("fields", [])
        response_fields = endpoint.get("response", {}).get("fields", [])
        for field in request_fields + response_fields:
            for key in ("name", "semanticId"):
                value = field.get(key)
                if value in ("", None):
                    errors.append(
                        f"{endpoint.get('operationId')} field '{field.get('name')}' missing {key}"
                    )
            semantic_id = field.get("semanticId")
            if semantic_id and semantic_id not in attribute_ids:
                errors.append(
                    f"{endpoint.get('operationId')} field '{field.get('name')}' "
                    f"references unknown semanticId '{semantic_id}'"
                )

    controls = inventory.get("controlsCatalog", [])
    if not isinstance(controls, list) or not controls:
        errors.append("inventory.controlsCatalog must be a non-empty list")

    for control in controls:
        for key in (
            "name",
            "kind",
            "description",
            "default",
            "exposure",
            "canonicalTerm",
            "semanticId",
        ):
            if key not in control:
                errors.append(f"control '{control.get('name')}' missing key {key}")

    semantic_to_names: dict[str, set[str]] = {}
    for endpoint in endpoints:
        for field in endpoint.get("request", {}).get("fields", []) + endpoint.get(
            "response", {}
        ).get("fields", []):
            semantic_id = field.get("semanticId")
            name = field.get("name")
            if not semantic_id or not name:
                continue
            semantic_to_names.setdefault(str(semantic_id), set()).add(
                _to_snake_case(_leaf_name(str(name)))
            )

    for semantic_id, names in semantic_to_names.items():
        if len(names) > 1:
            errors.append(
                f"semantic naming drift for {semantic_id}: multiple canonical names {sorted(names)}"
            )
    return errors


def main() -> int:
    parser = ArgumentParser(description="Generate/validate lotus-core API vocabulary inventory.")
    parser.add_argument("--output", type=Path, help="Write generated inventory JSON to this path.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate generated inventory without writing output.",
    )
    args = parser.parse_args()

    inventory = generate_inventory()
    errors = validate_inventory(inventory)

    if errors:
        print("API vocabulary inventory validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1

    if args.output and not args.validate_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(f"Wrote inventory: {args.output}")
    else:
        print("Inventory validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
