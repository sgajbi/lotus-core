from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    QUERY_CONTROL_PLANE_SERVICE,
    QUERY_SERVICE,
    SourceDataProductDefinition,
)
from scripts import source_data_product_contract_guard as guard


def _route(
    service: str,
    path: str,
    product_name: str | None,
    *,
    method: str = "GET",
) -> guard.SourceDataProductRoute:
    return guard.SourceDataProductRoute(
        service=service,
        method=method,
        path=path,
        source="src/services/query_service/app/routers/example.py",
        function_name="example_route",
        product_name=product_name,
    )


def _product(
    product_name: str,
    route: str,
    *,
    serving_plane: str = QUERY_SERVICE,
) -> SourceDataProductDefinition:
    return SourceDataProductDefinition(
        product_name=product_name,
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=serving_plane,
        owner="lotus-core",
        consumers=("lotus-performance",),
        current_routes=(route,),
    )


def test_evaluate_source_data_product_bindings_accepts_catalog_route_metadata() -> None:
    catalog = (_product("PortfolioTimeseriesInput", "/integration/example"),)
    routes = [_route(QUERY_SERVICE, "/integration/example", "PortfolioTimeseriesInput")]

    assert guard.evaluate_source_data_product_bindings(routes, catalog) == []


def test_evaluate_source_data_product_bindings_rejects_missing_catalog_route_metadata() -> None:
    catalog = (_product("PortfolioTimeseriesInput", "/integration/example"),)
    routes = [_route(QUERY_SERVICE, "/integration/example", None)]

    errors = guard.evaluate_source_data_product_bindings(routes, catalog)

    assert len(errors) == 1
    assert "must bind source-data product 'PortfolioTimeseriesInput', found None" in errors[0]


def test_evaluate_source_data_product_bindings_rejects_wrong_catalog_route_product() -> None:
    catalog = (
        _product("PortfolioTimeseriesInput", "/integration/example"),
        _product("PositionTimeseriesInput", "/integration/other"),
    )
    routes = [
        _route(QUERY_SERVICE, "/integration/example", "PositionTimeseriesInput"),
        _route(QUERY_SERVICE, "/integration/other", "PositionTimeseriesInput"),
    ]

    errors = guard.evaluate_source_data_product_bindings(routes, catalog)

    assert len(errors) == 2
    assert "must bind source-data product 'PortfolioTimeseriesInput'" in errors[0]
    assert "not listed in that product's current_routes" in errors[1]


def test_evaluate_source_data_product_bindings_rejects_unknown_product_metadata() -> None:
    routes = [_route(QUERY_SERVICE, "/integration/example", "UnknownProduct")]

    errors = guard.evaluate_source_data_product_bindings(routes, ())

    assert len(errors) == 1
    assert "binds unknown source-data product" in errors[0]


def test_evaluate_source_data_product_bindings_rejects_wrong_serving_plane() -> None:
    catalog = (
        _product(
            "PortfolioTimeseriesInput",
            "/integration/example",
            serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        ),
    )
    routes = [
        _route(
            QUERY_SERVICE,
            "/integration/example",
            "PortfolioTimeseriesInput",
        )
    ]

    errors = guard.evaluate_source_data_product_bindings(routes, catalog)

    assert len(errors) == 2
    assert "query_control_plane_service /integration/example is listed" in errors[0]
    assert "not 'query_service'" in errors[1]


def test_discover_source_data_product_routes_finds_current_catalog_bindings() -> None:
    discovered = guard.discover_source_data_product_routes()
    product_routes = {
        (route.service, route.path, route.product_name)
        for route in discovered
        if route.product_name
    }

    assert (
        QUERY_CONTROL_PLANE_SERVICE,
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
        "PortfolioTimeseriesInput",
    ) in product_routes
    assert (
        QUERY_SERVICE,
        "/portfolios/{portfolio_id}/transactions",
        "TransactionLedgerWindow",
    ) in product_routes
