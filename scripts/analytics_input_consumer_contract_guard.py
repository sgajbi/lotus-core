"""Validate RFC-0082/RFC-0083 analytics consumer contract bindings."""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from portfolio_common.source_data_products import (
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
    OPERATIONAL_READ,
    QUERY_CONTROL_PLANE_SERVICE,
    QUERY_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
    SNAPSHOT_AND_SIMULATION,
    SourceDataProductDefinition,
    products_for_consumer,
)
from src.services.query_service.app.dtos.analytics_input_dto import CashFlowObservation


LOTUS_PERFORMANCE = "lotus-performance"
LOTUS_RISK = "lotus-risk"

LOTUS_PERFORMANCE_REQUIRED_PRODUCTS = {
    "PortfolioTimeseriesInput",
    "PositionTimeseriesInput",
    "PortfolioAnalyticsReference",
    "MarketDataWindow",
    "InstrumentReferenceBundle",
    "BenchmarkAssignment",
    "BenchmarkConstituentWindow",
    "IndexSeriesWindow",
    "RiskFreeSeriesWindow",
    "ReconciliationEvidenceBundle",
    "DataQualityCoverageReport",
}

LOTUS_RISK_REQUIRED_PRODUCTS = {
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
    "IndexSeriesWindow",
    "RiskFreeSeriesWindow",
    "ReconciliationEvidenceBundle",
    "DataQualityCoverageReport",
}

LOTUS_PERFORMANCE_ALLOWED_FAMILIES = {
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
}

LOTUS_RISK_ALLOWED_FAMILIES = {
    SNAPSHOT_AND_SIMULATION,
    OPERATIONAL_READ,
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
}

EXPECTED_SERVING_PLANE_BY_FAMILY = {
    SNAPSHOT_AND_SIMULATION: QUERY_CONTROL_PLANE_SERVICE,
    OPERATIONAL_READ: QUERY_SERVICE,
    ANALYTICS_INPUT: QUERY_CONTROL_PLANE_SERVICE,
    CONTROL_PLANE_AND_POLICY: QUERY_CONTROL_PLANE_SERVICE,
}

ANALYTICS_CASH_FLOW_TYPES = {
    "external_flow",
    "internal_trade_flow",
    "income",
    "fee",
    "transfer",
    "other",
}


def _cash_flow_type_enum() -> set[str]:
    schema = CashFlowObservation.model_json_schema()
    cash_flow_type = schema["properties"]["cash_flow_type"]
    values = cash_flow_type.get("enum")
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def _evaluate_consumer_contracts(
    *,
    consumer: str,
    required_products: set[str],
    allowed_families: set[str],
    allowed_route_prefixes: tuple[str, ...],
    catalog: tuple[SourceDataProductDefinition, ...],
    required_serving_plane: str | None = None,
) -> list[str]:
    consumer_products = products_for_consumer(consumer, catalog=catalog)
    product_names = {product.product_name for product in consumer_products}
    errors: list[str] = []

    missing_products = required_products - product_names
    if missing_products:
        errors.append(
            f"{consumer} is missing required source-data product(s): "
            + ", ".join(sorted(missing_products))
        )

    unexpected_products = product_names - required_products
    if unexpected_products:
        errors.append(
            f"{consumer} is bound to unexpected source-data product(s): "
            + ", ".join(sorted(unexpected_products))
        )

    for product in consumer_products:
        expected_serving_plane = required_serving_plane or EXPECTED_SERVING_PLANE_BY_FAMILY.get(
            product.route_family
        )
        if product.route_family not in allowed_families:
            errors.append(
                f"{product.product_name} has unsupported {consumer} route family "
                f"{product.route_family!r}"
            )
        if expected_serving_plane and product.serving_plane != expected_serving_plane:
            errors.append(
                f"{product.product_name} must be served by {expected_serving_plane}, "
                f"found {product.serving_plane}"
            )
        for route in product.current_routes:
            if not route.startswith(allowed_route_prefixes):
                errors.append(
                    f"{product.product_name} route {route!r} is not a governed consumer route"
                )

    return errors


def evaluate_lotus_performance_contracts(
    *,
    catalog: tuple[SourceDataProductDefinition, ...] = SOURCE_DATA_PRODUCT_CATALOG,
    cash_flow_types: set[str] | None = None,
) -> list[str]:
    errors = _evaluate_consumer_contracts(
        consumer=LOTUS_PERFORMANCE,
        required_products=LOTUS_PERFORMANCE_REQUIRED_PRODUCTS,
        allowed_families=LOTUS_PERFORMANCE_ALLOWED_FAMILIES,
        allowed_route_prefixes=("/integration/", "/support/"),
        catalog=catalog,
        required_serving_plane=QUERY_CONTROL_PLANE_SERVICE,
    )

    resolved_cash_flow_types = (
        cash_flow_types if cash_flow_types is not None else _cash_flow_type_enum()
    )
    if resolved_cash_flow_types != ANALYTICS_CASH_FLOW_TYPES:
        errors.append(
            "analytics cash_flow_type vocabulary must be "
            f"{sorted(ANALYTICS_CASH_FLOW_TYPES)}, found {sorted(resolved_cash_flow_types)}"
        )
    if "expense" in resolved_cash_flow_types:
        errors.append('analytics cash_flow_type vocabulary must not expose legacy "expense"')

    return errors


def evaluate_lotus_risk_contracts(
    *,
    catalog: tuple[SourceDataProductDefinition, ...] = SOURCE_DATA_PRODUCT_CATALOG,
) -> list[str]:
    return _evaluate_consumer_contracts(
        consumer=LOTUS_RISK,
        required_products=LOTUS_RISK_REQUIRED_PRODUCTS,
        allowed_families=LOTUS_RISK_ALLOWED_FAMILIES,
        allowed_route_prefixes=("/integration/", "/support/", "/portfolios/", "/reporting/"),
        catalog=catalog,
    )


def main() -> int:
    errors = evaluate_lotus_performance_contracts() + evaluate_lotus_risk_contracts()
    if errors:
        print("Analytics input consumer contract guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Analytics input consumer contract guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
