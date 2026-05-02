import json
from pathlib import Path

import pytest
from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
    DEFAULT_REQUIRED_METADATA_FIELDS,
    DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG,
    OPERATIONAL_READ,
    QUERY_CONTROL_PLANE_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
    SourceDataProductDefinition,
    get_source_data_product,
    planned_products_for_consumer,
    products_for_consumer,
    source_data_product_openapi_extra,
    validate_source_data_product_catalog,
)


def test_source_data_product_catalog_is_valid() -> None:
    validate_source_data_product_catalog()


def test_catalog_contains_priority_rfc_0083_products() -> None:
    product_names = {product.product_name for product in SOURCE_DATA_PRODUCT_CATALOG}

    assert {
        "PortfolioStateSnapshot",
        "HoldingsAsOf",
        "TransactionLedgerWindow",
        "PositionTimeseriesInput",
        "PortfolioTimeseriesInput",
        "PortfolioAnalyticsReference",
        "MarketDataWindow",
        "InstrumentReferenceBundle",
        "BenchmarkAssignment",
        "BenchmarkConstituentWindow",
        "DpmModelPortfolioTarget",
        "IndexSeriesWindow",
        "RiskFreeSeriesWindow",
        "ReconciliationEvidenceBundle",
        "DataQualityCoverageReport",
        "IngestionEvidenceBundle",
    } <= product_names


def test_dpm_planned_source_products_are_governed_but_not_active_routes() -> None:
    active_product_names = {product.product_name for product in SOURCE_DATA_PRODUCT_CATALOG}
    planned_products = {
        product.product_name: product for product in DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG
    }

    assert planned_products.keys() == {
        "DiscretionaryMandateBinding",
        "InstrumentEligibilityProfile",
        "PortfolioTaxLotWindow",
        "MarketDataCoverageWindow",
    }
    assert not set(planned_products) & active_product_names
    assert all(product.owner == "lotus-core" for product in planned_products.values())
    assert all(product.consumers == ("lotus-manage",) for product in planned_products.values())
    assert all(
        product.serving_plane == QUERY_CONTROL_PLANE_SERVICE
        for product in planned_products.values()
    )
    assert all(product.route_family == ANALYTICS_INPUT for product in planned_products.values())
    assert all(
        route.startswith("/integration/")
        and "execution-context" not in route
        and "dpm-execution-context" not in route
        for product in planned_products.values()
        for route in product.current_routes
    )
    validate_source_data_product_catalog(DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG)


def test_dpm_planned_source_products_are_reserved_for_lotus_manage() -> None:
    product_names = {
        product.product_name for product in planned_products_for_consumer("lotus-manage")
    }

    assert product_names == {
        "DiscretionaryMandateBinding",
        "InstrumentEligibilityProfile",
        "PortfolioTaxLotWindow",
        "MarketDataCoverageWindow",
    }
    assert planned_products_for_consumer("lotus-performance") == ()


def test_get_source_data_product_is_case_insensitive() -> None:
    product = get_source_data_product(" positiontimeseriesinput ")

    assert product.product_name == "PositionTimeseriesInput"
    assert product.route_family == ANALYTICS_INPUT
    assert product.serving_plane == QUERY_CONTROL_PLANE_SERVICE
    assert "/integration/portfolios/{portfolio_id}/analytics/position-timeseries" in (
        product.current_routes
    )


def test_products_for_consumer_maps_performance_to_analytics_inputs() -> None:
    products = products_for_consumer("lotus-performance")
    product_names = {product.product_name for product in products}

    assert "PortfolioTimeseriesInput" in product_names
    assert "PositionTimeseriesInput" in product_names
    assert "PortfolioAnalyticsReference" in product_names
    assert "HoldingsAsOf" not in product_names
    assert all(
        product.route_family in {ANALYTICS_INPUT, CONTROL_PLANE_AND_POLICY} for product in products
    )


def test_catalog_keeps_performance_snapshot_outputs_out_of_core() -> None:
    product_names = {product.product_name for product in SOURCE_DATA_PRODUCT_CATALOG}
    performance_products = products_for_consumer("lotus-performance")

    assert "PortfolioPerformanceSnapshot" not in product_names
    assert "PerformanceSnapshot" not in product_names
    assert all(
        not product.product_name.endswith(("ReturnSnapshot", "PerformanceSnapshot"))
        for product in performance_products
    )
    assert all(product.owner == "lotus-core" for product in performance_products)


def test_source_data_product_openapi_extra_exposes_machine_readable_contract_identity() -> None:
    extra = source_data_product_openapi_extra("PortfolioTimeseriesInput")

    extension = extra["x-lotus-source-data-product"]

    assert extension["product_name"] == "PortfolioTimeseriesInput"
    assert extension["product_version"] == "v1"
    assert extension["route_family"] == ANALYTICS_INPUT
    assert extension["serving_plane"] == QUERY_CONTROL_PLANE_SERVICE
    assert extension["owner"] == "lotus-core"
    assert "lotus-performance" in extension["consumers"]
    assert (
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries"
        in extension["current_routes"]
    )
    assert "required_metadata_fields" in extension
    assert "restatement_version" in extension["required_metadata_fields"]

    security_extension = extra["x-lotus-source-data-security"]
    assert security_extension["product_name"] == "PortfolioTimeseriesInput"
    assert security_extension["tenant_required"] is True
    assert security_extension["entitlement_required"] is True
    assert security_extension["access_classification"] == "system_access"
    assert security_extension["audit_requirement"] == "audit_system_access"
    assert (
        security_extension["required_capability"] == "source_data.portfolio_timeseries_input.read"
    )


def test_holdings_product_records_convenience_shapes_to_consolidate() -> None:
    product = get_source_data_product("HoldingsAsOf")

    assert product.route_family == OPERATIONAL_READ
    assert "/portfolios/{portfolio_id}/cash-balances" in product.current_routes
    assert product.replaces_convenience_shapes == ()


def test_catalog_current_routes_are_registered_contract_routes() -> None:
    registry = json.loads(Path("docs/standards/route-contract-family-registry.json").read_text())
    registered_routes = {
        route.split(" ", maxsplit=1)[1]
        for service_routes in registry["routes"].values()
        for family_routes in service_routes.values()
        for route in family_routes
    }

    catalog_routes = {
        route for product in SOURCE_DATA_PRODUCT_CATALOG for route in product.current_routes
    }

    assert catalog_routes <= registered_routes


def test_catalog_rejects_duplicate_product_names() -> None:
    duplicate = SourceDataProductDefinition(
        product_name="PortfolioStateSnapshot",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance",),
        current_routes=("/integration/example",),
    )

    with pytest.raises(ValueError, match="Duplicate source-data product"):
        validate_source_data_product_catalog(SOURCE_DATA_PRODUCT_CATALOG + (duplicate,))


def test_catalog_rejects_duplicate_routes() -> None:
    existing_route = get_source_data_product("PortfolioStateSnapshot").current_routes[0]
    duplicate = SourceDataProductDefinition(
        product_name="DuplicateRouteProduct",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance",),
        current_routes=(existing_route,),
    )

    with pytest.raises(ValueError, match="assigned to both"):
        validate_source_data_product_catalog(SOURCE_DATA_PRODUCT_CATALOG + (duplicate,))


def test_catalog_rejects_missing_required_supportability_metadata() -> None:
    incomplete = SourceDataProductDefinition(
        product_name="IncompleteProduct",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance",),
        current_routes=("/integration/incomplete",),
        required_metadata_fields=tuple(
            field for field in DEFAULT_REQUIRED_METADATA_FIELDS if field != "restatement_version"
        ),
    )

    with pytest.raises(ValueError, match="restatement_version"):
        validate_source_data_product_catalog((incomplete,))


def test_unknown_product_lookup_fails_loudly() -> None:
    with pytest.raises(KeyError, match="Unknown source-data product"):
        get_source_data_product("UnknownProduct")
