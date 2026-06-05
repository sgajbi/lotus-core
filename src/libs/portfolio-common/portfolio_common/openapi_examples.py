"""Shared OpenAPI schema example and description inference."""

from __future__ import annotations

import re
from copy import deepcopy
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

_DATE_EXAMPLE = "2026-02-27"
_DATE_TIME_EXAMPLE = "2026-02-27T10:30:00Z"
_NUMBER_EXAMPLE_RULES = (
    (("weight",), 0.125),
    (("price", "rate"), 1.2345),
    (("quantity",), 100.0),
    (("pnl", "amount", "value"), 125000.5),
)
_STRING_LIKE_EXAMPLE_RULES = (
    (("currency",), "USD"),
    (("date",), _DATE_EXAMPLE),
    (("time", "timestamp"), _DATE_TIME_EXAMPLE),
    (("status",), "ACTIVE"),
)


def to_snake_case(value: str) -> str:
    transformed = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    transformed = transformed.replace("-", "_").replace(" ", "_")
    return transformed.lower()


def humanize(key: str) -> str:
    return to_snake_case(key).replace("_", " ").strip()


def infer_example(prop_name: str, prop_schema: dict[str, Any]) -> Any:
    key = to_snake_case(prop_name)
    schema_type = prop_schema.get("type")
    for example in (
        _known_key_example(key),
        _enum_example(prop_schema),
        _typed_example(prop_name=prop_name, key=key, prop_schema=prop_schema),
        _formatted_example(prop_schema),
    ):
        if example is not None:
            return example

    return _infer_string_like_example(key=key, schema_type=schema_type)


def _known_key_example(key: str) -> Any:
    return _EXAMPLE_BY_KEY.get(key)


def _enum_example(prop_schema: dict[str, Any]) -> Any:
    enum_values = prop_schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    return None


def _typed_example(*, prop_name: str, key: str, prop_schema: dict[str, Any]) -> Any:
    schema_type = prop_schema.get("type")
    if schema_type in _STATIC_TYPED_EXAMPLES:
        return _STATIC_TYPED_EXAMPLES[schema_type]
    if schema_type in _DYNAMIC_TYPED_EXAMPLE_BUILDERS:
        return _DYNAMIC_TYPED_EXAMPLE_BUILDERS[schema_type](prop_name, key, prop_schema)
    return None


def _array_example(prop_name: str, _key: str, prop_schema: dict[str, Any]) -> list[Any]:
    return [infer_example(f"{prop_name}_item", prop_schema.get("items", {}))]


def _integer_example(_prop_name: str, key: str, _prop_schema: dict[str, Any]) -> int:
    return _infer_integer_example(key)


def _number_example(_prop_name: str, key: str, _prop_schema: dict[str, Any]) -> float:
    return _infer_number_example(key)


_STATIC_TYPED_EXAMPLES = {
    "object": {"key": "value"},
    "boolean": True,
}
_DYNAMIC_TYPED_EXAMPLE_BUILDERS = {
    "array": _array_example,
    "integer": _integer_example,
    "number": _number_example,
}


def _formatted_example(prop_schema: dict[str, Any]) -> str | None:
    schema_format = prop_schema.get("format")
    if schema_format == "date":
        return _DATE_EXAMPLE
    if schema_format == "date-time":
        return _DATE_TIME_EXAMPLE
    return None


def _infer_integer_example(key: str) -> int:
    if "ttl" in key or "hours" in key:
        return 24
    if "version" in key:
        return 1
    return 10


def _infer_number_example(key: str) -> float:
    for tokens, example in _NUMBER_EXAMPLE_RULES:
        if _key_contains_any(key, tokens):
            return example
    return 10.5


def _infer_string_like_example(*, key: str, schema_type: object) -> str:
    identifier_example = _identifier_string_example(key)
    if identifier_example is not None:
        return identifier_example
    pattern_example = _string_pattern_example(key)
    if pattern_example is not None:
        return pattern_example
    if schema_type == "string":
        return f"example_{key}"
    return f"{key}_example"


def _identifier_string_example(key: str) -> str | None:
    if key.endswith("_id"):
        entity = key[: -len("_id")]
        return f"{entity.upper()}_001"
    return None


def _string_pattern_example(key: str) -> str | None:
    for tokens, example in _STRING_LIKE_EXAMPLE_RULES:
        if _key_contains_any(key, tokens):
            return example
    return None


def _key_contains_any(key: str, tokens: tuple[str, ...]) -> bool:
    return any(token in key for token in tokens)


def infer_description(model_name: str, prop_name: str, prop_schema: dict[str, Any]) -> str:
    key = to_snake_case(prop_name)
    text = humanize(prop_name)
    description = _rule_based_description(key=key, text=text, prop_schema=prop_schema)
    if description is not None:
        return description
    return f"{humanize(model_name)} field: {text}."


def _rule_based_description(
    *,
    key: str,
    text: str,
    prop_schema: dict[str, Any],
) -> str | None:
    description_rules = (
        (_is_identifier_field, _identifier_description),
        (_is_business_date_field, _business_date_description),
        (_is_timestamp_field, _timestamp_description),
        (_is_currency_field, _currency_description),
        (_is_monetary_field, _monetary_description),
        (_is_quantity_field, _quantity_description),
        (_is_rate_or_price_field, _rate_or_price_description),
        (_is_status_field, _status_description),
    )
    for predicate, describe in description_rules:
        if predicate(key, prop_schema):
            return describe(key, text)
    return None


def _is_identifier_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return key.endswith("_id")


def _identifier_description(key: str, _text: str) -> str:
    entity = key[: -len("_id")].replace("_", " ")
    return f"Unique {entity} identifier."


def _is_business_date_field(key: str, prop_schema: dict[str, Any]) -> bool:
    return "date" in key and prop_schema.get("format") == "date"


def _business_date_description(_key: str, text: str) -> str:
    return f"Business date for {text}."


def _is_timestamp_field(key: str, prop_schema: dict[str, Any]) -> bool:
    return "time" in key or prop_schema.get("format") == "date-time"


def _timestamp_description(_key: str, text: str) -> str:
    return f"Timestamp for {text}."


def _is_currency_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return "currency" in key


def _currency_description(_key: str, text: str) -> str:
    return f"ISO currency code for {text}."


def _is_monetary_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return "amount" in key or "value" in key or "pnl" in key


def _monetary_description(_key: str, text: str) -> str:
    return f"Monetary value for {text}."


def _is_quantity_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return "quantity" in key


def _quantity_description(_key: str, text: str) -> str:
    return f"Quantity value for {text}."


def _is_rate_or_price_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return "rate" in key or "price" in key


def _rate_or_price_description(_key: str, text: str) -> str:
    return f"Rate/price value for {text}."


def _is_status_field(key: str, _prop_schema: dict[str, Any]) -> bool:
    return "status" in key


def _status_description(_key: str, text: str) -> str:
    return f"Current status for {text}."


def resolve_ref_schema(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {}
    current: Any = root_schema
    for segment in ref.removeprefix("#/").split("/"):
        if not isinstance(current, dict):
            return {}
        current = current.get(segment)
    return current if isinstance(current, dict) else {}


def build_schema_example(
    schema_node: dict[str, Any] | None,
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None = None,
) -> Any:
    if not isinstance(schema_node, dict):
        return None

    explicit_example = _explicit_schema_example(schema_node)
    if explicit_example is not None:
        return explicit_example

    ref_example = _build_ref_example(
        schema_node,
        root_schema=root_schema,
        seen_refs=seen_refs,
    )
    if ref_example is not None:
        return ref_example

    union_example = _build_union_example(
        schema_node,
        root_schema=root_schema,
        seen_refs=seen_refs,
    )
    if union_example is not None:
        return union_example

    schema_type = schema_node.get("type")
    if schema_type == "object" or "properties" in schema_node:
        return _build_object_example(schema_node, root_schema=root_schema, seen_refs=seen_refs)
    if schema_type == "array":
        return _build_array_example(schema_node, root_schema=root_schema, seen_refs=seen_refs)

    title = schema_node.get("title")
    prop_name = title if isinstance(title, str) and title else "value"
    return infer_example(prop_name, schema_node)


def _explicit_schema_example(schema_node: dict[str, Any]) -> Any:
    if "example" in schema_node:
        return deepcopy(schema_node["example"])
    examples = schema_node.get("examples")
    if isinstance(examples, list) and examples:
        return deepcopy(examples[0])
    return None


def _build_ref_example(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> Any:
    ref = schema_node.get("$ref")
    if not isinstance(ref, str):
        return None
    if seen_refs is None:
        seen_refs = set()
    if ref in seen_refs:
        return None
    next_seen_refs = set(seen_refs)
    next_seen_refs.add(ref)
    return build_schema_example(
        resolve_ref_schema(root_schema, ref),
        root_schema=root_schema,
        seen_refs=next_seen_refs,
    )


def _build_union_example(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> Any:
    for union_key in ("allOf", "oneOf", "anyOf"):
        variants = schema_node.get(union_key)
        if not isinstance(variants, list) or not variants:
            continue
        value = _build_all_of_example(variants, root_schema=root_schema, seen_refs=seen_refs)
        if union_key == "allOf" and value:
            return value
        if union_key != "allOf":
            value = _first_available_variant_example(
                variants,
                root_schema=root_schema,
                seen_refs=seen_refs,
            )
            if value is not None:
                return value
    return None


def _build_all_of_example(
    variants: list[Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for variant in variants:
        value = build_schema_example(variant, root_schema=root_schema, seen_refs=seen_refs)
        if isinstance(value, dict):
            merged.update(value)
    return merged


def _first_available_variant_example(
    variants: list[Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> Any:
    for variant in variants:
        value = build_schema_example(variant, root_schema=root_schema, seen_refs=seen_refs)
        if value is not None:
            return value
    return None


def _build_object_example(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> dict[str, Any]:
    properties = schema_node.get("properties", {})
    if not isinstance(properties, dict):
        return {}
    example: dict[str, Any] = {}
    required = set(schema_node.get("required", []))
    for prop_name, prop_schema in properties.items():
        value = build_schema_example(prop_schema, root_schema=root_schema, seen_refs=seen_refs)
        if value is None and prop_name not in required:
            continue
        if value is None and isinstance(prop_schema, dict):
            value = infer_example(prop_name, prop_schema)
        example[prop_name] = value
    return example


def _build_array_example(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    seen_refs: set[str] | None,
) -> list[Any]:
    item_schema = schema_node.get("items", {})
    value = build_schema_example(item_schema, root_schema=root_schema, seen_refs=seen_refs)
    return [] if value is None else [value]
