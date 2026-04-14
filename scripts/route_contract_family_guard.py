"""Validate RFC-0082 route contract-family classification."""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "docs" / "standards" / "route-contract-family-registry.json"
REGISTRY_SPEC_VERSION = "1.0.0"
APPLICATION = "lotus-core"
GOVERNING_RFCS = {"RFC-0082", "RFC-0083"}

ROUTER_ROOTS = {
    "event_replay_service": REPO_ROOT
    / "src"
    / "services"
    / "event_replay_service"
    / "app"
    / "routers",
    "financial_reconciliation_service": REPO_ROOT
    / "src"
    / "services"
    / "financial_reconciliation_service"
    / "app"
    / "routers",
    "ingestion_service": REPO_ROOT / "src" / "services" / "ingestion_service" / "app" / "routers",
    "query_control_plane_service": REPO_ROOT
    / "src"
    / "services"
    / "query_control_plane_service"
    / "app"
    / "routers",
    "query_service": REPO_ROOT / "src" / "services" / "query_service" / "app" / "routers",
}

ROUTE_METHODS = {"delete", "get", "patch", "post", "put"}
ROUTE_METHODS_UPPER = {method.upper() for method in ROUTE_METHODS}
VALID_FAMILIES = {
    "Analytics Input",
    "Control Execution",
    "Control-Plane And Policy",
    "Operational Read",
    "Snapshot And Simulation",
    "Write Ingress",
}

FAMILY_PLANES = {
    "Analytics Input": "analytics_input_plane",
    "Control Execution": "control_execution_plane",
    "Control-Plane And Policy": "control_plane_and_policy",
    "Operational Read": "operational_read_plane",
    "Snapshot And Simulation": "snapshot_and_simulation_plane",
    "Write Ingress": "write_ingress_plane",
}


@dataclass(frozen=True)
class Route:
    service: str
    method: str
    path: str
    source: str
    function_name: str

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


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


def _extract_routes_from_file(service: str, router_file: Path) -> list[Route]:
    tree = ast.parse(router_file.read_text(encoding="utf-8"))
    prefix = _router_prefix(tree)
    routes: list[Route] = []
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
            if decorator.func.value.id != "router":
                continue
            if decorator.func.attr not in ROUTE_METHODS:
                continue
            route_path = ""
            if decorator.args:
                route_path = _literal_string(decorator.args[0]) or ""
            for keyword in decorator.keywords:
                if keyword.arg == "path":
                    route_path = _literal_string(keyword.value) or route_path
            routes.append(
                Route(
                    service=service,
                    method=decorator.func.attr.upper(),
                    path=_join_paths(prefix, route_path),
                    source=router_file.relative_to(REPO_ROOT).as_posix(),
                    function_name=node.name,
                )
            )
    return routes


def discover_routes() -> list[Route]:
    routes: list[Route] = []
    for service, root in sorted(ROUTER_ROOTS.items()):
        for router_file in sorted(root.glob("*.py")):
            routes.extend(_extract_routes_from_file(service, router_file))
    return sorted(routes, key=lambda route: (route.service, route.key, route.source))


def _load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, set[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("specVersion") != REGISTRY_SPEC_VERSION:
        raise ValueError(f"route registry specVersion must be {REGISTRY_SPEC_VERSION!r}")
    if payload.get("application") != APPLICATION:
        raise ValueError(f"route registry application must be {APPLICATION!r}")
    if set(payload.get("governingRfcs", [])) != GOVERNING_RFCS:
        raise ValueError("route registry governingRfcs must contain RFC-0082 and RFC-0083")
    registry: dict[str, dict[str, set[str]]] = {}
    routes_payload = payload.get("routes", {})
    if not isinstance(routes_payload, dict):
        raise ValueError("route registry must contain an object at routes")
    unknown_services = set(routes_payload) - set(ROUTER_ROOTS)
    if unknown_services:
        raise ValueError(
            "route registry contains unknown services: " + ", ".join(sorted(unknown_services))
        )
    for service, family_map in routes_payload.items():
        if not isinstance(service, str) or not isinstance(family_map, dict):
            raise ValueError(f"invalid registry service entry: {service!r}")
        registry[service] = {}
        for family, route_keys in family_map.items():
            if family not in VALID_FAMILIES:
                raise ValueError(f"invalid route family {family!r} for {service}")
            if not isinstance(route_keys, list):
                raise ValueError(f"registry routes for {service}/{family} must be a list")
            validated_route_keys = [_require_route_key(item) for item in route_keys]
            duplicate_route_keys = {
                route_key
                for route_key in validated_route_keys
                if validated_route_keys.count(route_key) > 1
            }
            if duplicate_route_keys:
                raise ValueError(
                    f"duplicate route keys in {service}/{family}: "
                    + ", ".join(sorted(duplicate_route_keys))
                )
            registry[service][family] = set(validated_route_keys)
    return registry


def _require_route_key(item: Any) -> str:
    if not isinstance(item, str) or " /" not in item:
        raise ValueError(f"invalid route key {item!r}")
    method, path = item.split(" ", 1)
    if method not in ROUTE_METHODS_UPPER:
        raise ValueError(f"invalid route method in route key {item!r}")
    if not path.startswith("/"):
        raise ValueError(f"route path must start with / in route key {item!r}")
    return item


def _registry_keys(registry: dict[str, dict[str, set[str]]]) -> dict[str, str]:
    route_to_family: dict[str, str] = {}
    for service, family_map in registry.items():
        for family, route_keys in family_map.items():
            for route_key in route_keys:
                full_key = f"{service} {route_key}"
                if full_key in route_to_family:
                    raise ValueError(f"duplicate route registry entry for {full_key}")
                route_to_family[full_key] = family
    return route_to_family


def evaluate_routes(
    discovered_routes: list[Route], registry: dict[str, dict[str, set[str]]]
) -> list[str]:
    try:
        registry_keys = _registry_keys(registry)
    except ValueError as exc:
        return [str(exc)]
    discovered_keys = {f"{route.service} {route.key}": route for route in discovered_routes}
    errors: list[str] = []

    for full_key, route in sorted(discovered_keys.items()):
        if full_key not in registry_keys:
            errors.append(
                f"{route.source}:{route.function_name}: {route.service} {route.key} "
                "is missing from docs/standards/route-contract-family-registry.json"
            )

    for full_key, family in sorted(registry_keys.items()):
        if full_key not in discovered_keys:
            errors.append(f"{full_key} is registered as {family} but no active router defines it")

    for full_key, family in sorted(registry_keys.items()):
        if family not in FAMILY_PLANES:
            errors.append(f"{full_key} has no RFC-0083 plane mapping for family {family}")

    return errors


def main() -> int:
    registry = _load_registry()
    errors = evaluate_routes(discover_routes(), registry)
    if errors:
        print("Route contract-family guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Route contract-family guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
