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
    QUERY_CONTROL_PLANE_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
    SourceDataProductDefinition,
    products_for_consumer,
)
from src.services.query_service.app.dtos.analytics_input_dto import CashFlowObservation


LOTUS_PERFORMANCE = "lotus-performance"

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

LOTUS_PERFORMANCE_ALLOWED_FAMILIES = {
    ANALYTICS_INPUT,
    CONTROL_PLANE_AND_POLICY,
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


def evaluate_lotus_performance_contracts(
    *,
    catalog: tuple[SourceDataProductDefinition, ...] = SOURCE_DATA_PRODUCT_CATALOG,
    cash_flow_types: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    performance_products = products_for_consumer(LOTUS_PERFORMANCE, catalog=catalog)
    product_names = {product.product_name for product in performance_products}

    missing_products = LOTUS_PERFORMANCE_REQUIRED_PRODUCTS - product_names
    if missing_products:
        errors.append(
            "lotus-performance is missing required source-data product(s): "
            + ", ".join(sorted(missing_products))
        )

    unexpected_products = product_names - LOTUS_PERFORMANCE_REQUIRED_PRODUCTS
    if unexpected_products:
        errors.append(
            "lotus-performance is bound to unexpected source-data product(s): "
            + ", ".join(sorted(unexpected_products))
        )

    for product in performance_products:
        if product.serving_plane != QUERY_CONTROL_PLANE_SERVICE:
            errors.append(
                f"{product.product_name} must be served by {QUERY_CONTROL_PLANE_SERVICE}, "
                f"found {product.serving_plane}"
            )
        if product.route_family not in LOTUS_PERFORMANCE_ALLOWED_FAMILIES:
            errors.append(
                f"{product.product_name} has unsupported lotus-performance route family "
                f"{product.route_family!r}"
            )
        for route in product.current_routes:
            if not route.startswith(("/integration/", "/support/")):
                errors.append(
                    f"{product.product_name} route {route!r} is not a governed control-plane "
                    "consumer route"
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


def main() -> int:
    errors = evaluate_lotus_performance_contracts()
    if errors:
        print("Analytics input consumer contract guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Analytics input consumer contract guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
