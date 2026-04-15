"""Validate RFC-0083 source-data product route and response metadata bindings."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from portfolio_common.source_data_products import (
    SOURCE_DATA_PRODUCT_CATALOG,
    SourceDataProductDefinition,
    source_data_product_openapi_extra,
    validate_source_data_product_catalog,
)
from portfolio_common.source_data_security import get_source_data_security_profile


REPO_ROOT = Path(__file__).resolve().parents[1]

ROUTER_ROOTS = {
    "query_control_plane_service": REPO_ROOT
    / "src"
    / "services"
    / "query_control_plane_service"
    / "app"
    / "routers",
    "query_service": REPO_ROOT / "src" / "services" / "query_service" / "app" / "routers",
}

DTO_ROOT = REPO_ROOT / "src" / "services" / "query_service" / "app" / "dtos"
ROUTE_METHODS = {"delete", "get", "patch", "post", "put"}


@dataclass(frozen=True)
class SourceDataProductRoute:
    service: str
    method: str
    path: str
    source: str
    function_name: str
    product_name: str | None
    response_model: str | None

    @property
    def route_key(self) -> str:
        return f"{self.service} {self.path}"

    @property
    def diagnostic_key(self) -> str:
        return f"{self.source}:{self.function_name}: {self.service} {self.method} {self.path}"


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _router_prefix(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "router" for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for keyword in node.value.keywords:
            if keyword.arg == "prefix":
                return _literal_string(keyword.value) or ""
    return ""


def _join_paths(prefix: str, route_path: str) -> str:
    full_path = f"{prefix.rstrip('/')}/{route_path.lstrip('/')}".rstrip("/")
    return full_path or "/"


def _source_data_product_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        function_name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        function_name = node.func.attr
    else:
        return None
    if function_name != "source_data_product_openapi_extra" or not node.args:
        return None
    return _literal_string(node.args[0])


def _name_or_attribute(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_routes_from_file(service: str, router_file: Path) -> list[SourceDataProductRoute]:
    tree = ast.parse(router_file.read_text(encoding="utf-8"))
    prefix = _router_prefix(tree)
    routes: list[SourceDataProductRoute] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "router" or decorator.func.attr not in ROUTE_METHODS:
                continue

            route_path = ""
            if decorator.args:
                route_path = _literal_string(decorator.args[0]) or ""
            product_name: str | None = None
            response_model: str | None = None
            for keyword in decorator.keywords:
                if keyword.arg == "path":
                    route_path = _literal_string(keyword.value) or route_path
                if keyword.arg == "openapi_extra":
                    product_name = _source_data_product_name(keyword.value)
                if keyword.arg == "response_model":
                    response_model = _name_or_attribute(keyword.value)

            routes.append(
                SourceDataProductRoute(
                    service=service,
                    method=decorator.func.attr.upper(),
                    path=_join_paths(prefix, route_path),
                    source=router_file.relative_to(REPO_ROOT).as_posix(),
                    function_name=node.name,
                    product_name=product_name,
                    response_model=response_model,
                )
            )
    return routes


def discover_source_data_product_routes() -> list[SourceDataProductRoute]:
    routes: list[SourceDataProductRoute] = []
    for service, root in sorted(ROUTER_ROOTS.items()):
        for router_file in sorted(root.glob("*.py")):
            routes.extend(_extract_routes_from_file(service, router_file))
    return sorted(routes, key=lambda route: (route.service, route.path, route.method))


def _product_identity_field_value(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    function_name = _name_or_attribute(node.func)
    if function_name == "product_name_field" and node.args:
        return _literal_string(node.args[0])
    if function_name == "product_version_field":
        return "v1"
    return None


def discover_response_model_product_identities(
    dto_root: Path = DTO_ROOT,
) -> dict[str, tuple[str | None, str | None]]:
    identities: dict[str, tuple[str | None, str | None]] = {}
    for dto_file in sorted(dto_root.glob("*.py")):
        tree = ast.parse(dto_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            product_name: str | None = None
            product_version: str | None = None
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                if not isinstance(statement.target, ast.Name):
                    continue
                if statement.target.id == "product_name":
                    product_name = _product_identity_field_value(statement.value)
                if statement.target.id == "product_version":
                    product_version = _product_identity_field_value(statement.value)
            if product_name is not None or product_version is not None:
                identities[node.name] = (product_name, product_version)
    return identities


def evaluate_source_data_product_bindings(
    routes: list[SourceDataProductRoute],
    catalog: tuple[SourceDataProductDefinition, ...] = SOURCE_DATA_PRODUCT_CATALOG,
    response_model_identities: dict[str, tuple[str | None, str | None]] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        validate_source_data_product_catalog(catalog)
    except ValueError as exc:
        errors.append(f"source-data product catalog is invalid: {exc}")

    response_model_identities = response_model_identities or {}
    expected_route_products = {
        f"{product.serving_plane} {route}": product.product_name
        for product in catalog
        for route in product.current_routes
    }
    products_by_name = {product.product_name: product for product in catalog}
    discovered_by_route_key = {route.route_key: route for route in routes}

    for route_key, expected_product_name in sorted(expected_route_products.items()):
        route = discovered_by_route_key.get(route_key)
        if route is None:
            errors.append(f"{route_key} is listed in the source-data product catalog but missing")
            continue
        if route.product_name != expected_product_name:
            errors.append(
                f"{route.diagnostic_key} must bind source-data product "
                f"{expected_product_name!r}, found {route.product_name!r}"
            )
        if route.response_model is None:
            errors.append(f"{route.diagnostic_key} must declare a response_model")
            continue
        response_identity = response_model_identities.get(route.response_model)
        if response_identity is None:
            errors.append(
                f"{route.diagnostic_key} response model {route.response_model!r} must declare "
                f"product identity for {expected_product_name!r}"
            )
            continue
        response_product_name, response_product_version = response_identity
        if response_product_name != expected_product_name:
            errors.append(
                f"{route.diagnostic_key} response model {route.response_model!r} must declare "
                f"product_name {expected_product_name!r}, found {response_product_name!r}"
            )
        expected_version = products_by_name[expected_product_name].product_version
        if response_product_version != expected_version:
            errors.append(
                f"{route.diagnostic_key} response model {route.response_model!r} must declare "
                f"product_version {expected_version!r}, found {response_product_version!r}"
            )

    for route in routes:
        if route.product_name is None:
            continue
        product = products_by_name.get(route.product_name)
        if product is None:
            errors.append(f"{route.diagnostic_key} binds unknown source-data product")
            continue
        if product.serving_plane != route.service:
            errors.append(
                f"{route.diagnostic_key} binds {product.product_name!r} for serving plane "
                f"{product.serving_plane!r}, not {route.service!r}"
            )
        if route.path not in product.current_routes:
            errors.append(
                f"{route.diagnostic_key} binds {product.product_name!r} but the route is not "
                "listed in that product's current_routes"
            )

    for product in catalog:
        extra = source_data_product_openapi_extra(product.product_name)
        security_extension = extra.get("x-lotus-source-data-security")
        if not isinstance(security_extension, dict):
            errors.append(
                f"{product.product_name} source-data product OpenAPI metadata must expose "
                "x-lotus-source-data-security"
            )
            continue
        profile = get_source_data_security_profile(product.product_name)
        expected_security = {
            "product_name": profile.product_name,
            "tenant_required": profile.tenant_required,
            "entitlement_required": profile.entitlement_required,
            "access_classification": profile.access_classification,
            "sensitivity_classification": profile.sensitivity_classification,
            "retention_requirement": profile.retention_requirement,
            "audit_requirement": profile.audit_requirement,
            "pii_fields": list(profile.pii_fields),
            "operator_only": profile.operator_only,
        }
        if security_extension != expected_security:
            errors.append(
                f"{product.product_name} source-data product OpenAPI security metadata must "
                "match its governed source-data security profile"
            )

    return errors


def main() -> int:
    errors = evaluate_source_data_product_bindings(
        discover_source_data_product_routes(),
        response_model_identities=discover_response_model_product_identities(),
    )
    if errors:
        print("Source-data product contract guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Source-data product contract guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
