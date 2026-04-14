from scripts import route_contract_family_guard as guard


def _route(service: str, method: str, path: str) -> guard.Route:
    return guard.Route(
        service=service,
        method=method,
        path=path,
        source="src/services/example/app/routers/example.py",
        function_name="example_route",
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


def test_require_route_key_rejects_invalid_method() -> None:
    try:
        guard._require_route_key("TRACE /portfolios")
    except ValueError as exc:
        assert "invalid route method" in str(exc)
    else:
        raise AssertionError("TRACE should not be accepted as a registry route method")


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
