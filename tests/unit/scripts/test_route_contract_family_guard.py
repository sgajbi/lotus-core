import json
from pathlib import Path

import pytest

from scripts import route_contract_family_guard as guard


def _route(
    service: str,
    method: str,
    path: str,
    *,
    source: str = "src/services/example/app/routers/example.py",
    function_name: str = "example_route",
) -> guard.Route:
    return guard.Route(
        service=service,
        method=method,
        path=path,
        source=source,
        function_name=function_name,
    )


def _write_registry(path: Path, routes: dict[str, dict[str, list[str]]]) -> None:
    path.write_text(
        json.dumps(
            {
                "specVersion": "1.0.0",
                "application": "lotus-core",
                "governingRfcs": ["RFC-0082", "RFC-0083"],
                "routes": routes,
            }
        ),
        encoding="utf-8",
    )


def test_evaluate_routes_rejects_unregistered_route() -> None:
    errors = guard.evaluate_routes(
        [_route("query_service", "GET", "/new-route")],
        {"query_service": {"Operational Read": set()}},
    )

    assert len(errors) == 1
    assert "is missing from docs/standards/route-contract-family-registry.json" in errors[0]


def test_evaluate_routes_rejects_stale_registry_route() -> None:
    errors = guard.evaluate_routes(
        [],
        {"query_service": {"Operational Read": {"GET /missing-route"}}},
    )

    assert len(errors) == 1
    assert "is registered as Operational Read but no active router defines it" in errors[0]


def test_evaluate_routes_rejects_duplicate_family_classification() -> None:
    errors = guard.evaluate_routes(
        [_route("query_control_plane_service", "GET", "/integration/capabilities")],
        {
            "query_control_plane_service": {
                "Analytics Input": {"GET /integration/capabilities"},
                "Control-Plane And Policy": {"GET /integration/capabilities"},
            }
        },
    )

    assert len(errors) == 1
    assert (
        "duplicate route registry entry for "
        "query_control_plane_service GET /integration/capabilities"
    ) in errors[0]


def test_evaluate_routes_rejects_duplicate_active_route_definition() -> None:
    errors = guard.evaluate_routes(
        [
            _route(
                "query_service",
                "GET",
                "/portfolios",
                source="src/services/query_service/app/routers/portfolio.py",
                function_name="list_portfolios",
            ),
            _route(
                "query_service",
                "GET",
                "/portfolios",
                source="src/services/query_service/app/routers/portfolio_legacy.py",
                function_name="list_portfolios_legacy",
            ),
        ],
        {"query_service": {"Operational Read": {"GET /portfolios"}}},
    )

    assert len(errors) == 1
    assert (
        "query_service GET /portfolios is defined by multiple active router handlers" in errors[0]
    )
    assert "list_portfolios" in errors[0]
    assert "list_portfolios_legacy" in errors[0]


def test_require_route_key_rejects_invalid_method() -> None:
    with pytest.raises(ValueError, match="invalid route method"):
        guard._require_route_key("TRACE /portfolios")


def test_load_registry_rejects_unknown_service(tmp_path: Path) -> None:
    registry_path = tmp_path / "route-contract-family-registry.json"
    _write_registry(
        registry_path,
        {"unknown_service": {"Operational Read": ["GET /portfolios"]}},
    )

    with pytest.raises(ValueError, match="unknown services: unknown_service"):
        guard._load_registry(registry_path)


def test_load_registry_rejects_duplicate_route_inside_family(tmp_path: Path) -> None:
    registry_path = tmp_path / "route-contract-family-registry.json"
    _write_registry(
        registry_path,
        {
            "query_service": {
                "Operational Read": ["GET /portfolios", "GET /portfolios"],
            }
        },
    )

    with pytest.raises(ValueError, match="duplicate route keys in query_service/Operational Read"):
        guard._load_registry(registry_path)


def test_evaluate_routes_accepts_registered_route() -> None:
    errors = guard.evaluate_routes(
        [_route("query_service", "GET", "/portfolios")],
        {"query_service": {"Operational Read": {"GET /portfolios"}}},
    )

    assert errors == []


def test_discover_routes_includes_core_router_roots() -> None:
    roots = set(guard.ROUTER_ROOTS)

    assert roots == {
        "event_replay_service",
        "financial_reconciliation_service",
        "ingestion_service",
        "query_control_plane_service",
        "query_service",
    }
