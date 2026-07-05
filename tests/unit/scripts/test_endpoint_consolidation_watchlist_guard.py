from pathlib import Path

import pytest

from scripts import endpoint_consolidation_watchlist_guard as guard
from scripts import route_contract_family_guard, source_data_product_contract_guard


def _route(
    service: str,
    method: str,
    path: str,
    *,
    source: str = "src/services/query_service/app/routers/example.py",
    function_name: str = "example_route",
) -> route_contract_family_guard.Route:
    return route_contract_family_guard.Route(
        service=service,
        method=method,
        path=path,
        source=source,
        function_name=function_name,
    )


def _source_route(
    service: str,
    method: str,
    path: str,
    product_name: str | None,
) -> source_data_product_contract_guard.SourceDataProductRoute:
    return source_data_product_contract_guard.SourceDataProductRoute(
        service=service,
        method=method,
        path=path,
        source="src/services/query_service/app/routers/example.py",
        function_name="example_route",
        product_name=product_name,
        response_model="ExampleResponse",
    )


def _active_entry(
    service: str = "query_service",
    method: str = "GET",
    path: str = "/portfolios/{portfolio_id}/cashflow-projection",
    *,
    route_family: str = "Operational Read",
    product_required: bool = True,
    source_data_products: tuple[str, ...] = ("PortfolioCashflowProjection",),
) -> guard.ActiveWatchlistRoute:
    return guard.ActiveWatchlistRoute(
        route=guard.RouteKey(service=service, method=method, path=path),
        route_family=route_family,
        disposition="keep_source_data_product",
        owner="lotus-core",
        source_data_product_required=product_required,
        source_data_products=source_data_products,
        approved_rationale="Core owns this bounded source route.",
        boundary_guardrail="Do not add consumer-specific behavior.",
        consumer_guidance="Use named source-data products for durable consumption.",
    )


def _watchlist(
    *,
    monitored_routes: tuple[guard.MonitoredRoute, ...] | None = None,
    active_routes: tuple[guard.ActiveWatchlistRoute, ...] | None = None,
    retired_routes: tuple[guard.RetiredWatchlistRoute, ...] = (),
) -> guard.EndpointConsolidationWatchlist:
    return guard.EndpointConsolidationWatchlist(
        monitored_routes=monitored_routes
        if monitored_routes is not None
        else (
            guard.MonitoredRoute(
                service="query_service",
                method="GET",
                path="/portfolios/{portfolio_id}/cashflow-projection",
                path_prefix=None,
            ),
        ),
        active_routes=active_routes if active_routes is not None else (_active_entry(),),
        retired_routes=retired_routes,
    )


def test_current_endpoint_consolidation_watchlist_passes() -> None:
    errors = guard.evaluate_watchlist(
        guard.load_watchlist(),
        route_contract_family_guard.discover_routes(),
        source_data_product_contract_guard.discover_source_data_product_routes(),
    )

    assert errors == []


def test_evaluate_watchlist_rejects_monitored_route_without_disposition() -> None:
    watchlist = _watchlist(active_routes=())
    route = _route("query_service", "GET", "/portfolios/{portfolio_id}/cashflow-projection")

    errors = guard.evaluate_watchlist(
        watchlist,
        [route],
        [],
        {"query_service GET /portfolios/{portfolio_id}/cashflow-projection": "Analytics Input"},
    )

    assert len(errors) == 1
    assert "matches an endpoint consolidation monitored family" in errors[0]
    assert "has no active watchlist disposition" in errors[0]


def test_evaluate_watchlist_rejects_missing_source_product_identity() -> None:
    watchlist = _watchlist()
    route = _route("query_service", "GET", "/portfolios/{portfolio_id}/cashflow-projection")

    errors = guard.evaluate_watchlist(
        watchlist,
        [route],
        [
            _source_route(
                "query_service",
                "GET",
                "/portfolios/{portfolio_id}/cashflow-projection",
                None,
            )
        ],
        {"query_service GET /portfolios/{portfolio_id}/cashflow-projection": "Operational Read"},
    )

    assert len(errors) == 1
    assert "must bind one of sourceDataProducts" in errors[0]
    assert "found None" in errors[0]


def test_evaluate_watchlist_accepts_bounded_route_with_approved_rationale() -> None:
    route = _route("query_service", "POST", "/reporting/portfolio-summary/query")
    watchlist = _watchlist(
        monitored_routes=(
            guard.MonitoredRoute(
                service="query_service",
                method="POST",
                path=None,
                path_prefix="/reporting/",
            ),
        ),
        active_routes=(
            _active_entry(
                method="POST",
                path="/reporting/portfolio-summary/query",
                route_family="Operational Read",
                product_required=False,
                source_data_products=("PortfolioStateSnapshot",),
            ),
        ),
    )

    errors = guard.evaluate_watchlist(
        watchlist,
        [route],
        [_source_route("query_service", "POST", "/reporting/portfolio-summary/query", None)],
        {"query_service POST /reporting/portfolio-summary/query": "Operational Read"},
    )

    assert errors == []


def test_evaluate_watchlist_rejects_retired_route_still_defined() -> None:
    retired_route = guard.RouteKey(
        service="query_service",
        method="POST",
        path="/reporting/income-summary/query",
    )
    watchlist = _watchlist(
        monitored_routes=(),
        active_routes=(),
        retired_routes=(
            guard.RetiredWatchlistRoute(
                route=retired_route,
                former_route_family="Operational Read",
                replacement_routes=("GET /portfolios/{portfolio_id}/transactions",),
                disposition="retired_after_consumer_migration",
                removal_evidence="Removed after migration.",
            ),
        ),
    )

    errors = guard.evaluate_watchlist(
        watchlist,
        [_route("query_service", "POST", "/reporting/income-summary/query")],
        [],
        {},
    )

    assert len(errors) == 1
    assert "is retired in watchlist but still has a router" in errors[0]


def test_evaluate_watchlist_rejects_duplicate_active_entry() -> None:
    route = _route("query_service", "GET", "/portfolios/{portfolio_id}/cashflow-projection")

    errors = guard.evaluate_watchlist(
        _watchlist(active_routes=(_active_entry(), _active_entry())),
        [route],
        [
            _source_route(
                "query_service",
                "GET",
                "/portfolios/{portfolio_id}/cashflow-projection",
                "PortfolioCashflowProjection",
            )
        ],
        {"query_service GET /portfolios/{portfolio_id}/cashflow-projection": "Operational Read"},
    )

    assert "duplicate active endpoint watchlist entries" in errors[0]


def test_load_watchlist_rejects_monitor_with_path_and_prefix(tmp_path: Path) -> None:
    path = tmp_path / "endpoint-consolidation-watchlist.json"
    path.write_text(
        """
{
  "specVersion": "1.0.0",
  "application": "lotus-core",
  "governingRfcs": ["RFC-0067", "RFC-0082", "RFC-0083"],
  "monitoredRoutes": [
    {
      "service": "query_service",
      "method": "POST",
      "path": "/reporting/example",
      "pathPrefix": "/reporting/",
      "reason": "invalid"
    }
  ],
  "activeWatchlistRoutes": [],
  "retiredRoutes": []
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="either path or pathPrefix"):
        guard.load_watchlist(path)
