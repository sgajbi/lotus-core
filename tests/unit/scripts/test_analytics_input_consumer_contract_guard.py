from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    OPERATIONAL_READ,
    QUERY_CONTROL_PLANE_SERVICE,
    QUERY_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
    SourceDataProductDefinition,
)
from scripts import analytics_input_consumer_contract_guard as guard


def _product(
    product_name: str,
    *,
    route: str = "/integration/example",
    route_family: str = ANALYTICS_INPUT,
    serving_plane: str = QUERY_CONTROL_PLANE_SERVICE,
    consumers: tuple[str, ...] = ("lotus-performance",),
) -> SourceDataProductDefinition:
    return SourceDataProductDefinition(
        product_name=product_name,
        product_version="v1",
        route_family=route_family,
        serving_plane=serving_plane,
        owner="lotus-core",
        consumers=consumers,
        current_routes=(route,),
    )


def _performance_catalog(
    *,
    overrides: tuple[SourceDataProductDefinition, ...] = (),
) -> tuple[SourceDataProductDefinition, ...]:
    override_names = {product.product_name for product in overrides}
    products = tuple(
        _product(product_name)
        for product_name in sorted(guard.LOTUS_PERFORMANCE_REQUIRED_PRODUCTS - override_names)
    )
    return products + overrides


def test_lotus_performance_contract_guard_accepts_current_catalog() -> None:
    assert guard.evaluate_lotus_performance_contracts() == []


def test_lotus_performance_contract_guard_rejects_missing_required_product() -> None:
    catalog = tuple(
        product
        for product in _performance_catalog()
        if product.product_name != "PortfolioTimeseriesInput"
    )

    errors = guard.evaluate_lotus_performance_contracts(
        catalog=catalog,
        cash_flow_types=guard.ANALYTICS_CASH_FLOW_TYPES,
    )

    assert any("PortfolioTimeseriesInput" in error for error in errors)


def test_lotus_performance_contract_guard_rejects_operational_read_binding() -> None:
    catalog = _performance_catalog(
        overrides=(
            _product(
                "PortfolioTimeseriesInput",
                route="/portfolios/{portfolio_id}/positions",
                route_family=OPERATIONAL_READ,
                serving_plane=QUERY_SERVICE,
            ),
        )
    )

    errors = guard.evaluate_lotus_performance_contracts(
        catalog=catalog,
        cash_flow_types=guard.ANALYTICS_CASH_FLOW_TYPES,
    )

    assert any("must be served by query_control_plane_service" in error for error in errors)
    assert any("unsupported lotus-performance route family" in error for error in errors)
    assert any("not a governed control-plane consumer route" in error for error in errors)


def test_lotus_performance_contract_guard_rejects_unexpected_product() -> None:
    catalog = _performance_catalog(overrides=(_product("UnexpectedPerformanceProduct"),))

    errors = guard.evaluate_lotus_performance_contracts(
        catalog=catalog,
        cash_flow_types=guard.ANALYTICS_CASH_FLOW_TYPES,
    )

    assert any("UnexpectedPerformanceProduct" in error for error in errors)


def test_lotus_performance_contract_guard_rejects_legacy_expense_cash_flow_type() -> None:
    cash_flow_types = set(guard.ANALYTICS_CASH_FLOW_TYPES)
    cash_flow_types.remove("fee")
    cash_flow_types.add("expense")

    errors = guard.evaluate_lotus_performance_contracts(
        catalog=_performance_catalog(),
        cash_flow_types=cash_flow_types,
    )

    assert any("cash_flow_type vocabulary" in error for error in errors)
    assert any('must not expose legacy "expense"' in error for error in errors)


def test_lotus_performance_current_products_are_explicitly_control_plane_only() -> None:
    products = {
        product.product_name: product
        for product in SOURCE_DATA_PRODUCT_CATALOG
        if "lotus-performance" in product.consumers
    }

    assert set(products) == guard.LOTUS_PERFORMANCE_REQUIRED_PRODUCTS
    assert all(
        product.serving_plane == QUERY_CONTROL_PLANE_SERVICE for product in products.values()
    )
