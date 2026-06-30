"""Shared OpenAPI enrichment utilities for Lotus services."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from portfolio_common.openapi_examples import (
    build_schema_example,
    infer_description,
    infer_example,
)

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _iter_operations(schema: dict[str, Any]):
    paths = schema.get("paths", {})
    for path, methods in paths.items():
        for method, operation in _path_operations(methods):
            yield path, method, operation


def _path_operations(methods: Any):
    if not isinstance(methods, dict):
        return
    for method, operation in methods.items():
        if _is_http_operation(method, operation):
            yield method, operation


def _is_http_operation(method: Any, operation: Any) -> bool:
    return (
        isinstance(method, str) and method.lower() in _HTTP_METHODS and isinstance(operation, dict)
    )


def _ensure_parameter_examples(schema: dict[str, Any]) -> None:
    for _, _, operation in _iter_operations(schema):
        for parameter in operation.get("parameters", []):
            if not isinstance(parameter, dict):
                continue
            _ensure_parameter_example(parameter)


def _ensure_parameter_example(parameter: dict[str, Any]) -> None:
    param_schema = parameter.get("schema")
    if not _should_add_parameter_example(parameter, param_schema):
        return
    explicit_example = _explicit_parameter_schema_example(param_schema)
    if explicit_example is not None:
        parameter["example"] = explicit_example
        return
    name = parameter.get("name")
    if isinstance(name, str):
        parameter["example"] = infer_example(name, param_schema)


def _should_add_parameter_example(parameter: dict[str, Any], param_schema: Any) -> bool:
    return (
        isinstance(param_schema, dict)
        and "example" not in parameter
        and "examples" not in parameter
    )


def _explicit_parameter_schema_example(param_schema: dict[str, Any]) -> Any:
    if "example" in param_schema:
        return deepcopy(param_schema["example"])
    examples = param_schema.get("examples")
    if isinstance(examples, list) and examples:
        return deepcopy(examples[0])
    return None


def _ensure_operation_examples(schema: dict[str, Any]) -> None:
    for _, _, operation in _iter_operations(schema):
        _ensure_request_body_examples(operation, root_schema=schema)
        _ensure_response_examples(operation, root_schema=schema)


def _ensure_request_body_examples(
    operation: dict[str, Any],
    *,
    root_schema: dict[str, Any],
) -> None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return
    for media_type, media_content in request_body.get("content", {}).items():
        _ensure_media_content_example(
            media_type=media_type,
            media_content=media_content,
            root_schema=root_schema,
        )


def _ensure_response_examples(
    operation: dict[str, Any],
    *,
    root_schema: dict[str, Any],
) -> None:
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return
    for response in responses.values():
        if not isinstance(response, dict):
            continue
        for media_type, media_content in response.get("content", {}).items():
            _ensure_media_content_example(
                media_type=media_type,
                media_content=media_content,
                root_schema=root_schema,
            )


def _ensure_media_content_example(
    *,
    media_type: str,
    media_content: Any,
    root_schema: dict[str, Any],
) -> None:
    if not _should_add_media_content_example(media_type, media_content):
        return
    example = build_schema_example(media_content.get("schema"), root_schema=root_schema)
    if example is not None:
        media_content["example"] = example


def _should_add_media_content_example(media_type: str, media_content: Any) -> bool:
    return (
        isinstance(media_content, dict)
        and "json" in media_type
        and "example" not in media_content
        and "examples" not in media_content
    )


def _ensure_operation_documentation(schema: dict[str, Any], service_name: str) -> None:
    for path, method, operation in _iter_operations(schema):
        if not operation.get("summary"):
            operation["summary"] = f"{method.upper()} {path}"
        if not operation.get("description"):
            operation["description"] = f"{method.upper()} operation for {path} in {service_name}."
        if not operation.get("tags"):
            operation["tags"] = [_infer_operation_tag(path)]
        _ensure_default_error_response(operation)


def _infer_operation_tag(path: str) -> str:
    if path.startswith("/health/"):
        return "Health"
    if path == "/metrics":
        return "Monitoring"
    segment = path.strip("/").split("/", 1)[0] or "default"
    return segment.replace("-", " ").title()


def _ensure_default_error_response(operation: dict[str, Any]) -> None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return
    if not _has_error_response(responses):
        responses["default"] = {
            "description": "Unexpected error response.",
        }


def _has_error_response(responses: dict[str, Any]) -> bool:
    return any(_is_error_response_code(code) for code in responses)


def _is_error_response_code(code: Any) -> bool:
    return isinstance(code, str) and (
        code.startswith("4") or code.startswith("5") or code == "default"
    )


def _ensure_schema_documentation(schema: dict[str, Any]) -> None:
    components = schema.get("components", {})
    schemas = components.get("schemas", {})
    for model_name, model_schema in schemas.items():
        _ensure_model_schema_documentation(
            model_name=model_name,
            model_schema=model_schema,
            root_schema=schema,
        )


def _ensure_model_schema_documentation(
    *,
    model_name: str,
    model_schema: Any,
    root_schema: dict[str, Any],
) -> None:
    if not isinstance(model_schema, dict):
        return
    properties = model_schema.get("properties", {})
    if not isinstance(properties, dict):
        return
    for prop_name, prop_schema in properties.items():
        if isinstance(prop_schema, dict):
            _ensure_property_documentation(
                model_name=model_name,
                prop_name=prop_name,
                prop_schema=prop_schema,
                root_schema=root_schema,
            )


def _ensure_property_documentation(
    *,
    model_name: str,
    prop_name: str,
    prop_schema: dict[str, Any],
    root_schema: dict[str, Any],
) -> None:
    if not prop_schema.get("description"):
        prop_schema["description"] = infer_description(model_name, prop_name, prop_schema)
    if "example" not in prop_schema:
        prop_schema["example"] = _build_property_example(prop_name, prop_schema, root_schema)


def _build_property_example(
    prop_name: str,
    prop_schema: dict[str, Any],
    root_schema: dict[str, Any],
) -> Any:
    complex_keys = ("$ref", "properties", "items", "allOf", "anyOf", "oneOf")
    if any(key in prop_schema for key in complex_keys) or prop_schema.get("type") in {
        "array",
        "object",
    }:
        example = build_schema_example(prop_schema, root_schema=root_schema)
        if example is not None:
            return example
    return infer_example(prop_name, prop_schema)


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
    _ensure_parameter_examples(schema)
    _ensure_operation_examples(schema)
    return schema


def attach_enriched_openapi(app: FastAPI, *, service_name: str) -> FastAPI:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _ensure_metrics_response_content(schema)
        schema = enrich_openapi_schema(schema, service_name=service_name)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
    return app


def _ensure_metrics_response_content(schema: dict[str, Any]) -> None:
    metrics_operation = schema.get("paths", {}).get("/metrics", {}).get("get")
    if not isinstance(metrics_operation, dict):
        return
    metrics_operation["summary"] = "Prometheus metrics scrape endpoint"
    metrics_operation["description"] = (
        "Operational Prometheus scrape endpoint. This is not a public business API; access is "
        "governed by the shared metrics access policy and should be reachable only by authorized "
        "scrapers or a private metrics network."
    )
    metrics_operation["tags"] = ["Monitoring"]
    responses = metrics_operation.setdefault("responses", {})
    metrics_response = responses.setdefault("200", {"description": "Prometheus metrics payload."})
    if isinstance(metrics_response, dict):
        metrics_response["content"] = {"text/plain": {"schema": {"type": "string"}}}
    responses.setdefault(
        "403",
        {
            "description": "Metrics scrape was denied by the shared metrics access policy.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "METRICS_ACCESS_DENIED",
                            "message": (
                                "Metrics endpoint access is restricted to authorized scrapers."
                            ),
                            "metrics_access_mode": "bearer_token",
                        }
                    }
                }
            },
        },
    )
