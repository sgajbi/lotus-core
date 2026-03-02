"""Shared OpenAPI enrichment utilities for Lotus services."""

from __future__ import annotations

import re
from typing import Any

_EXAMPLE_BY_KEY = {
    "portfolio_id": "DEMO_DPM_EUR_001",
    "session_id": "SIM_0001",
    "change_id": "CHG_0001",
    "security_id": "AAPL",
    "instrument_id": "EQ_US_AAPL",
    "transaction_id": "TXN_0001",
    "consumer_system": "lotus-manage",
    "tenant_id": "default",
    "policy_version": "tenant-default-v1",
    "currency": "USD",
    "base_currency": "USD",
    "as_of_date": "2026-02-27",
    "generated_at": "2026-02-27T10:30:00Z",
    "created_at": "2026-02-27T10:30:00Z",
    "effective_date": "2026-02-27",
    "status": "ACTIVE",
    "method": "POST",
    "path": "/portfolios/DEMO_DPM_EUR_001/positions",
    "workflow_key": "portfolio_bulk_onboarding",
    "contract_version": "v1",
    "source_service": "lotus-core",
    "asset_class": "Equity",
    "instrument_type": "CommonStock",
    "issuer_name": "Apple Inc.",
    "issuer_country": "US",
    "isin": "US0378331005",
    "cusip": "037833100",
    "sedol": "2046251",
    "ticker": "AAPL",
    "security_name": "Apple Inc. Common Stock",
    "price_date": "2026-02-27",
    "transaction_type": "BUY",
    "quantity": 100.0,
    "price": 182.35,
    "trade_fee": 7.5,
    "brokerage": 2.5,
    "stamp_duty": 1.2,
    "exchange_fee": 0.7,
    "gst": 0.45,
    "other_fees": 0.15,
    "gross_transaction_amount": 18235.0,
    "net_cost": 18242.5,
    "trade_currency": "USD",
    "from_currency": "USD",
    "to_currency": "SGD",
    "rate": 1.3524,
    "methodology": "EOD_CLOSE",
    "source_system": "OMS_PRIMARY",
    "correlation_id": "ING:1a2b3c4d-1234-5678-9abc-000000000001",
    "request_id": "REQ:1a2b3c4d-1234-5678-9abc-000000000001",
    "trace_id": "5f475bcbfb2c4fb68b1b6a2ed2d1c216",
}


def _to_snake_case(value: str) -> str:
    transformed = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    transformed = transformed.replace("-", "_").replace(" ", "_")
    return transformed.lower()


def _humanize(key: str) -> str:
    return _to_snake_case(key).replace("_", " ").strip()


def _infer_example(prop_name: str, prop_schema: dict[str, Any]) -> Any:
    key = _to_snake_case(prop_name)
    if key in _EXAMPLE_BY_KEY:
        return _EXAMPLE_BY_KEY[key]

    enum_values = prop_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    schema_type = prop_schema.get("type")
    schema_format = prop_schema.get("format")
    if schema_type == "array":
        item_schema = prop_schema.get("items", {})
        return [_infer_example(f"{prop_name}_item", item_schema)]
    if schema_type == "object":
        return {"key": "value"}
    if schema_type == "boolean":
        return True
    if schema_type == "integer":
        if "ttl" in key or "hours" in key:
            return 24
        if "version" in key:
            return 1
        return 10
    if schema_type == "number":
        if "weight" in key:
            return 0.125
        if "price" in key or "rate" in key:
            return 1.2345
        if "quantity" in key:
            return 100.0
        if "pnl" in key or "amount" in key or "value" in key:
            return 125000.5
        return 10.5

    if schema_format == "date":
        return "2026-02-27"
    if schema_format == "date-time":
        return "2026-02-27T10:30:00Z"

    if key.endswith("_id"):
        entity = key[: -len("_id")]
        return f"{entity.upper()}_001"
    if "currency" in key:
        return "USD"
    if "date" in key:
        return "2026-02-27"
    if "time" in key or "timestamp" in key:
        return "2026-02-27T10:30:00Z"
    if "status" in key:
        return "ACTIVE"
    if schema_type == "string":
        return f"example_{key}"
    return f"{key}_example"


def _infer_description(model_name: str, prop_name: str, prop_schema: dict[str, Any]) -> str:
    key = _to_snake_case(prop_name)
    text = _humanize(prop_name)
    if key.endswith("_id"):
        entity = key[: -len("_id")].replace("_", " ")
        return f"Unique {entity} identifier."
    if "date" in key and prop_schema.get("format") == "date":
        return f"Business date for {text}."
    if "time" in key or prop_schema.get("format") == "date-time":
        return f"Timestamp for {text}."
    if "currency" in key:
        return f"ISO currency code for {text}."
    if "amount" in key or "value" in key or "pnl" in key:
        return f"Monetary value for {text}."
    if "quantity" in key:
        return f"Quantity value for {text}."
    if "rate" in key or "price" in key:
        return f"Rate/price value for {text}."
    if "status" in key:
        return f"Current status for {text}."
    return f"{_humanize(model_name)} field: {text}."


def _ensure_operation_documentation(schema: dict[str, Any], service_name: str) -> None:
    paths = schema.get("paths", {})
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            if not operation.get("summary"):
                operation["summary"] = f"{method.upper()} {path}"
            if not operation.get("description"):
                operation["description"] = (
                    f"{method.upper()} operation for {path} in {service_name}."
                )
            if not operation.get("tags"):
                if path.startswith("/health/"):
                    operation["tags"] = ["Health"]
                elif path == "/metrics":
                    operation["tags"] = ["Monitoring"]
                else:
                    segment = path.strip("/").split("/", 1)[0] or "default"
                    operation["tags"] = [segment.replace("-", " ").title()]
            responses = operation.get("responses")
            if isinstance(responses, dict):
                has_error = any(
                    code.startswith("4") or code.startswith("5") or code == "default"
                    for code in responses
                )
                if not has_error:
                    responses["default"] = {
                        "description": "Unexpected error response.",
                    }


def _ensure_schema_documentation(schema: dict[str, Any]) -> None:
    components = schema.get("components", {})
    schemas = components.get("schemas", {})
    for model_name, model_schema in schemas.items():
        if not isinstance(model_schema, dict):
            continue
        properties = model_schema.get("properties", {})
        if not isinstance(properties, dict):
            continue
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            if not prop_schema.get("description"):
                prop_schema["description"] = _infer_description(model_name, prop_name, prop_schema)
            if "example" not in prop_schema:
                prop_schema["example"] = _infer_example(prop_name, prop_schema)


def enrich_openapi_schema(schema: dict[str, Any], service_name: str) -> dict[str, Any]:
    """Mutate schema in-place to ensure minimum documentation completeness."""
    info = schema.setdefault("info", {})
    info.setdefault("title", f"Lotus Core {service_name} API")
    if "lotus" not in (info.get("description") or "").lower():
        branded_desc = (info.get("description") or "").strip()
        prefix = "Lotus platform API contract."
        info["description"] = f"{prefix} {branded_desc}".strip()

    _ensure_operation_documentation(schema, service_name=service_name)
    _ensure_schema_documentation(schema)
    return schema
