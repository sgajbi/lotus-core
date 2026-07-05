"""Validate RFC-0083 endpoint consolidation watchlist ownership."""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

route_guard = importlib.import_module("route_contract_family_guard")
source_guard = importlib.import_module("source_data_product_contract_guard")

WATCHLIST_PATH = REPO_ROOT / "docs" / "standards" / "endpoint-consolidation-watchlist.json"
WATCHLIST_SPEC_VERSION = "1.0.0"
APPLICATION = "lotus-core"
GOVERNING_RFCS = {"RFC-0067", "RFC-0082", "RFC-0083"}


@dataclass(frozen=True)
class RouteKey:
    service: str
    method: str
    path: str

    @property
    def full_key(self) -> str:
        return f"{self.service} {self.method} {self.path}"

    @property
    def contract_key(self) -> str:
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class MonitoredRoute:
    service: str
    method: str
    path: str | None
    path_prefix: str | None

    def matches(self, route: RouteKey) -> bool:
        if route.service != self.service or route.method != self.method:
            return False
        if self.path is not None:
            return route.path == self.path
        if self.path_prefix is not None:
            return route.path.startswith(self.path_prefix)
        return False


@dataclass(frozen=True)
class ActiveWatchlistRoute:
    route: RouteKey
    route_family: str
    disposition: str
    owner: str
    source_data_product_required: bool
    source_data_products: tuple[str, ...]
    approved_rationale: str
    boundary_guardrail: str
    consumer_guidance: str


@dataclass(frozen=True)
class RetiredWatchlistRoute:
    route: RouteKey
    former_route_family: str
    replacement_routes: tuple[str, ...]
    disposition: str
    removal_evidence: str


@dataclass(frozen=True)
class EndpointConsolidationWatchlist:
    monitored_routes: tuple[MonitoredRoute, ...]
    active_routes: tuple[ActiveWatchlistRoute, ...]
    retired_routes: tuple[RetiredWatchlistRoute, ...]


def _require_non_empty_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must declare non-empty {field}")
    return value


def _require_route_key(payload: dict[str, Any], context: str) -> RouteKey:
    service = _require_non_empty_string(payload, "service", context)
    method = _require_non_empty_string(payload, "method", context)
    path = _require_non_empty_string(payload, "path", context)
    if service not in route_guard.ROUTER_ROOTS:
        raise ValueError(f"{context} declares unknown service {service!r}")
    if method not in route_guard.ROUTE_METHODS_UPPER:
        raise ValueError(f"{context} declares invalid method {method!r}")
    if not path.startswith("/"):
        raise ValueError(f"{context} path must start with /")
    return RouteKey(service=service, method=method, path=path)


def _require_string_tuple(payload: dict[str, Any], field: str, context: str) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context} must declare non-empty {field}")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context} {field} must contain non-empty strings")
        values.append(item)
    return tuple(values)


def _parse_monitored_route(payload: dict[str, Any], index: int) -> MonitoredRoute:
    context = f"monitoredRoutes[{index}]"
    service = _require_non_empty_string(payload, "service", context)
    method = _require_non_empty_string(payload, "method", context)
    if service not in route_guard.ROUTER_ROOTS:
        raise ValueError(f"{context} declares unknown service {service!r}")
    if method not in route_guard.ROUTE_METHODS_UPPER:
        raise ValueError(f"{context} declares invalid method {method!r}")
    path = payload.get("path")
    path_prefix = payload.get("pathPrefix")
    if isinstance(path, str) and isinstance(path_prefix, str):
        raise ValueError(f"{context} must declare either path or pathPrefix, not both")
    if path is None and path_prefix is None:
        raise ValueError(f"{context} must declare path or pathPrefix")
    if path is not None and (not isinstance(path, str) or not path.startswith("/")):
        raise ValueError(f"{context} path must start with /")
    if path_prefix is not None and (
        not isinstance(path_prefix, str) or not path_prefix.startswith("/")
    ):
        raise ValueError(f"{context} pathPrefix must start with /")
    _require_non_empty_string(payload, "reason", context)
    return MonitoredRoute(service=service, method=method, path=path, path_prefix=path_prefix)


def _parse_active_route(payload: dict[str, Any], index: int) -> ActiveWatchlistRoute:
    context = f"activeWatchlistRoutes[{index}]"
    source_data_product_required = payload.get("sourceDataProductRequired")
    if not isinstance(source_data_product_required, bool):
        raise ValueError(f"{context} must declare boolean sourceDataProductRequired")
    return ActiveWatchlistRoute(
        route=_require_route_key(payload, context),
        route_family=_require_non_empty_string(payload, "routeFamily", context),
        disposition=_require_non_empty_string(payload, "disposition", context),
        owner=_require_non_empty_string(payload, "owner", context),
        source_data_product_required=source_data_product_required,
        source_data_products=_require_string_tuple(payload, "sourceDataProducts", context),
        approved_rationale=_require_non_empty_string(payload, "approvedRationale", context),
        boundary_guardrail=_require_non_empty_string(payload, "boundaryGuardrail", context),
        consumer_guidance=_require_non_empty_string(payload, "consumerGuidance", context),
    )


def _parse_retired_route(payload: dict[str, Any], index: int) -> RetiredWatchlistRoute:
    context = f"retiredRoutes[{index}]"
    return RetiredWatchlistRoute(
        route=_require_route_key(payload, context),
        former_route_family=_require_non_empty_string(payload, "formerRouteFamily", context),
        replacement_routes=_require_string_tuple(payload, "replacementRoutes", context),
        disposition=_require_non_empty_string(payload, "disposition", context),
        removal_evidence=_require_non_empty_string(payload, "removalEvidence", context),
    )


def load_watchlist(path: Path = WATCHLIST_PATH) -> EndpointConsolidationWatchlist:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("specVersion") != WATCHLIST_SPEC_VERSION:
        raise ValueError(f"endpoint watchlist specVersion must be {WATCHLIST_SPEC_VERSION!r}")
    if payload.get("application") != APPLICATION:
        raise ValueError(f"endpoint watchlist application must be {APPLICATION!r}")
    if set(payload.get("governingRfcs", [])) != GOVERNING_RFCS:
        raise ValueError(
            "endpoint watchlist governingRfcs must contain RFC-0067, RFC-0082, RFC-0083"
        )
    return EndpointConsolidationWatchlist(
        monitored_routes=tuple(
            _parse_monitored_route(item, index)
            for index, item in enumerate(payload.get("monitoredRoutes", []))
            if isinstance(item, dict)
        ),
        active_routes=tuple(
            _parse_active_route(item, index)
            for index, item in enumerate(payload.get("activeWatchlistRoutes", []))
            if isinstance(item, dict)
        ),
        retired_routes=tuple(
            _parse_retired_route(item, index)
            for index, item in enumerate(payload.get("retiredRoutes", []))
            if isinstance(item, dict)
        ),
    )


def _duplicate_keys(keys: list[str]) -> set[str]:
    return {item for item, count in Counter(keys).items() if count > 1}


def _route_keys(discovered_routes: list[route_guard.Route]) -> dict[str, route_guard.Route]:
    return {
        RouteKey(route.service, route.method, route.path).full_key: route
        for route in discovered_routes
    }


def _source_product_by_route(
    source_routes: list[source_guard.SourceDataProductRoute],
) -> dict[str, source_guard.SourceDataProductRoute]:
    return {
        RouteKey(route.service, route.method, route.path).full_key: route for route in source_routes
    }


def _route_family_by_key() -> dict[str, str]:
    return route_guard._registry_keys(route_guard._load_registry())  # noqa: SLF001


def evaluate_watchlist(
    watchlist: EndpointConsolidationWatchlist,
    discovered_routes: list[route_guard.Route],
    source_routes: list[source_guard.SourceDataProductRoute],
    route_families: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    route_by_key = _route_keys(discovered_routes)
    source_product_by_route = _source_product_by_route(source_routes)
    route_families = route_families if route_families is not None else _route_family_by_key()

    active_keys = [entry.route.full_key for entry in watchlist.active_routes]
    retired_keys = [entry.route.full_key for entry in watchlist.retired_routes]
    for full_key in sorted(_duplicate_keys(active_keys)):
        errors.append(f"{full_key} has duplicate active endpoint watchlist entries")
    for full_key in sorted(_duplicate_keys(retired_keys)):
        errors.append(f"{full_key} has duplicate retired endpoint watchlist entries")
    for full_key in sorted(set(active_keys) & set(retired_keys)):
        errors.append(f"{full_key} cannot be both active and retired in endpoint watchlist")

    active_key_set = set(active_keys)
    for route in route_by_key.values():
        route_key = RouteKey(route.service, route.method, route.path)
        if any(monitored.matches(route_key) for monitored in watchlist.monitored_routes):
            if route_key.full_key not in active_key_set:
                errors.append(
                    f"{route.source}:{route.function_name}: {route_key.full_key} matches an "
                    "endpoint consolidation monitored family but has no active "
                    "watchlist disposition"
                )

    for entry in watchlist.active_routes:
        route = route_by_key.get(entry.route.full_key)
        if route is None:
            errors.append(f"{entry.route.full_key} is active in watchlist but no router defines it")
            continue
        actual_family = route_families.get(entry.route.full_key)
        if actual_family != entry.route_family:
            errors.append(
                f"{entry.route.full_key} watchlist routeFamily {entry.route_family!r} does not "
                f"match route-contract registry family {actual_family!r}"
            )
        source_product_route = source_product_by_route.get(entry.route.full_key)
        actual_product = (
            source_product_route.product_name if source_product_route is not None else None
        )
        if entry.source_data_product_required and actual_product not in entry.source_data_products:
            errors.append(
                f"{entry.route.full_key} must bind one of sourceDataProducts "
                f"{entry.source_data_products!r}, found {actual_product!r}"
            )
        if actual_product is not None and actual_product not in entry.source_data_products:
            errors.append(
                f"{entry.route.full_key} binds source-data product {actual_product!r} but the "
                "endpoint watchlist does not declare it"
            )
        if not entry.source_data_product_required and actual_product is None:
            if not entry.approved_rationale or not entry.boundary_guardrail:
                errors.append(
                    f"{entry.route.full_key} lacks source-data product identity and must carry "
                    "approvedRationale and boundaryGuardrail"
                )
            if not entry.consumer_guidance:
                errors.append(
                    f"{entry.route.full_key} lacks source-data product identity and must carry "
                    "consumerGuidance"
                )

    for entry in watchlist.retired_routes:
        if entry.route.full_key in route_by_key:
            errors.append(f"{entry.route.full_key} is retired in watchlist but still has a router")

    return errors


def main() -> int:
    errors = evaluate_watchlist(
        load_watchlist(),
        route_guard.discover_routes(),
        source_guard.discover_source_data_product_routes(),
    )
    if errors:
        print("Endpoint consolidation watchlist guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Endpoint consolidation watchlist guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
