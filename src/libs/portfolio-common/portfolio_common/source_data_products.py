"""RFC-0083 source-data product catalog helpers."""

from __future__ import annotations

from dataclasses import dataclass


CATALOG_VERSION = "2026-04-15"

OPERATIONAL_READ = "Operational Read"
SNAPSHOT_AND_SIMULATION = "Snapshot And Simulation"
ANALYTICS_INPUT = "Analytics Input"
CONTROL_PLANE_AND_POLICY = "Control-Plane And Policy"

QUERY_SERVICE = "query_service"
QUERY_CONTROL_PLANE_SERVICE = "query_control_plane_service"

INLINE_PAGED = "inline_paged"
EXPORT_ELIGIBLE = "export_eligible"
EXPORT_ONLY_FOR_LARGE_WINDOWS = "export_only_for_large_windows"
NOT_APPLICABLE = "not_applicable"

DEFAULT_REQUIRED_METADATA_FIELDS = (
    "product_name",
    "product_version",
    "tenant_id",
    "generated_at",
    "as_of_date",
    "restatement_version",
    "reconciliation_status",
    "data_quality_status",
    "latest_evidence_timestamp",
    "source_batch_fingerprint",
    "snapshot_id",
    "policy_version",
    "correlation_id",
)


@dataclass(frozen=True)
class SourceDataProductDefinition:
    product_name: str
    product_version: str
    route_family: str
    serving_plane: str
    owner: str
    consumers: tuple[str, ...]
    current_routes: tuple[str, ...]
    required_metadata_fields: tuple[str, ...] = DEFAULT_REQUIRED_METADATA_FIELDS
    paging_mode: str = INLINE_PAGED
    export_mode: str = NOT_APPLICABLE
    replaces_convenience_shapes: tuple[str, ...] = ()
    notes: str = ""


SOURCE_DATA_PRODUCT_CATALOG: tuple[SourceDataProductDefinition, ...] = (
    SourceDataProductDefinition(
        product_name="PortfolioStateSnapshot",
        product_version="v1",
        route_family=SNAPSHOT_AND_SIMULATION,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-gateway", "lotus-advise", "lotus-manage", "lotus-risk"),
        current_routes=("/integration/portfolios/{portfolio_id}/core-snapshot",),
        paging_mode=NOT_APPLICABLE,
        export_mode=NOT_APPLICABLE,
        notes="Policy-aware multi-section snapshot for baseline or simulation state.",
    ),
    SourceDataProductDefinition(
        product_name="HoldingsAsOf",
        product_version="v1",
        route_family=OPERATIONAL_READ,
        serving_plane=QUERY_SERVICE,
        owner="lotus-core",
        consumers=("lotus-gateway", "lotus-risk", "lotus-report", "lotus-manage"),
        current_routes=(
            "/portfolios/{portfolio_id}/positions",
            "/reporting/holdings-snapshot/query",
            "/reporting/cash-balances/query",
        ),
        replaces_convenience_shapes=(
            "/reporting/holdings-snapshot/query",
            "/reporting/cash-balances/query",
        ),
        notes="Canonical holdings and cash state for an as-of date.",
    ),
    SourceDataProductDefinition(
        product_name="TransactionLedgerWindow",
        product_version="v1",
        route_family=OPERATIONAL_READ,
        serving_plane=QUERY_SERVICE,
        owner="lotus-core",
        consumers=("lotus-gateway", "lotus-report", "lotus-manage", "lotus-risk"),
        current_routes=(
            "/portfolios/{portfolio_id}/transactions",
            "/reporting/activity-summary/query",
            "/reporting/income-summary/query",
        ),
        replaces_convenience_shapes=(
            "/reporting/activity-summary/query",
            "/reporting/income-summary/query",
        ),
        notes="Deterministically ordered transaction and income ledger window.",
    ),
    SourceDataProductDefinition(
        product_name="PositionTimeseriesInput",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=("/integration/portfolios/{portfolio_id}/analytics/position-timeseries",),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ELIGIBLE,
        notes="Position-level analytics input with valuation and cash-flow provenance.",
    ),
    SourceDataProductDefinition(
        product_name="PortfolioTimeseriesInput",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=("/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ELIGIBLE,
        notes="Portfolio-level valuation and cash-flow input for TWR/MWR workflows.",
    ),
    SourceDataProductDefinition(
        product_name="MarketDataWindow",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=("/integration/benchmarks/{benchmark_id}/market-series",),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ONLY_FOR_LARGE_WINDOWS,
        notes="Analytics-safe market-data window with observed and ingested timestamp lineage.",
    ),
    SourceDataProductDefinition(
        product_name="InstrumentReferenceBundle",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk", "lotus-gateway", "lotus-advise"),
        current_routes=(
            "/integration/instruments/enrichment-bulk",
            "/integration/reference/classification-taxonomy",
        ),
        notes="Instrument, issuer, taxonomy, and classification source reference.",
    ),
    SourceDataProductDefinition(
        product_name="BenchmarkAssignment",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk", "lotus-report"),
        current_routes=("/integration/portfolios/{portfolio_id}/benchmark-assignment",),
        notes="Effective benchmark assignment for a portfolio and as-of date.",
    ),
    SourceDataProductDefinition(
        product_name="BenchmarkConstituentWindow",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=("/integration/benchmarks/{benchmark_id}/composition-window",),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ONLY_FOR_LARGE_WINDOWS,
        notes="Effective benchmark constituent and weight segments across a requested window.",
    ),
    SourceDataProductDefinition(
        product_name="IndexSeriesWindow",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=(
            "/integration/indices/{index_id}/price-series",
            "/integration/indices/{index_id}/return-series",
        ),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ONLY_FOR_LARGE_WINDOWS,
        notes="Canonical index price and return source series.",
    ),
    SourceDataProductDefinition(
        product_name="RiskFreeSeriesWindow",
        product_version="v1",
        route_family=ANALYTICS_INPUT,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk"),
        current_routes=("/integration/reference/risk-free-series",),
        paging_mode=INLINE_PAGED,
        export_mode=EXPORT_ONLY_FOR_LARGE_WINDOWS,
        notes="Canonical risk-free rate source series for excess-return workflows.",
    ),
    SourceDataProductDefinition(
        product_name="ReconciliationEvidenceBundle",
        product_version="v1",
        route_family=CONTROL_PLANE_AND_POLICY,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk", "lotus-gateway", "lotus-manage"),
        current_routes=(
            "/support/portfolios/{portfolio_id}/reconciliation-runs",
            "/support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings",
        ),
        paging_mode=INLINE_PAGED,
        notes="Consumer-safe reconciliation run, finding, break, and blocking evidence.",
    ),
    SourceDataProductDefinition(
        product_name="DataQualityCoverageReport",
        product_version="v1",
        route_family=CONTROL_PLANE_AND_POLICY,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-performance", "lotus-risk", "lotus-gateway", "lotus-manage"),
        current_routes=(
            "/integration/benchmarks/{benchmark_id}/coverage",
            "/integration/reference/risk-free-series/coverage",
        ),
        paging_mode=NOT_APPLICABLE,
        notes="Completeness, freshness, and blocking coverage report for source products.",
    ),
    SourceDataProductDefinition(
        product_name="IngestionEvidenceBundle",
        product_version="v1",
        route_family=CONTROL_PLANE_AND_POLICY,
        serving_plane=QUERY_CONTROL_PLANE_SERVICE,
        owner="lotus-core",
        consumers=("lotus-gateway", "lotus-manage", "lotus-report"),
        current_routes=(
            "/lineage/portfolios/{portfolio_id}/keys",
            "/support/portfolios/{portfolio_id}/reprocessing-keys",
            "/support/portfolios/{portfolio_id}/reprocessing-jobs",
        ),
        paging_mode=INLINE_PAGED,
        notes="Source-batch, validation, replay, DLQ, quarantine, and repair evidence.",
    ),
)


def get_source_data_product(product_name: str) -> SourceDataProductDefinition:
    requested = _normalize_required_text(product_name, "product_name")
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.product_name.upper() == requested:
            return product
    raise KeyError(f"Unknown source-data product: {product_name}")


def source_data_product_openapi_extra(product_name: str) -> dict[str, dict[str, object]]:
    product = get_source_data_product(product_name)
    return {
        "x-lotus-source-data-product": {
            "product_name": product.product_name,
            "product_version": product.product_version,
            "route_family": product.route_family,
            "serving_plane": product.serving_plane,
            "owner": product.owner,
            "consumers": list(product.consumers),
            "current_routes": list(product.current_routes),
            "paging_mode": product.paging_mode,
            "export_mode": product.export_mode,
            "required_metadata_fields": list(product.required_metadata_fields),
        }
    }


def products_for_consumer(consumer: str) -> tuple[SourceDataProductDefinition, ...]:
    requested = _normalize_required_text(consumer, "consumer")
    return tuple(
        product
        for product in SOURCE_DATA_PRODUCT_CATALOG
        if requested in {item.upper() for item in product.consumers}
    )


def validate_source_data_product_catalog(
    catalog: tuple[SourceDataProductDefinition, ...] = SOURCE_DATA_PRODUCT_CATALOG,
) -> None:
    seen_names: set[str] = set()
    seen_routes: dict[str, str] = {}
    for product in catalog:
        normalized_name = _normalize_required_text(product.product_name, "product_name")
        if normalized_name in seen_names:
            raise ValueError(f"Duplicate source-data product: {product.product_name}")
        seen_names.add(normalized_name)
        _require_text(product.product_version, "product_version")
        _require_allowed(
            product.route_family,
            "route_family",
            {
                OPERATIONAL_READ,
                SNAPSHOT_AND_SIMULATION,
                ANALYTICS_INPUT,
                CONTROL_PLANE_AND_POLICY,
            },
        )
        _require_allowed(
            product.serving_plane,
            "serving_plane",
            {QUERY_SERVICE, QUERY_CONTROL_PLANE_SERVICE},
        )
        _require_allowed(
            product.paging_mode,
            "paging_mode",
            {INLINE_PAGED, NOT_APPLICABLE},
        )
        _require_allowed(
            product.export_mode,
            "export_mode",
            {EXPORT_ELIGIBLE, EXPORT_ONLY_FOR_LARGE_WINDOWS, NOT_APPLICABLE},
        )
        _require_text(product.owner, "owner")
        _require_non_empty_tuple(product.consumers, "consumers")
        _require_non_empty_tuple(product.current_routes, "current_routes")
        _require_required_metadata(product.required_metadata_fields)
        for route in product.current_routes:
            normalized_route = _normalize_required_text(route, "current_routes")
            if normalized_route in seen_routes:
                raise ValueError(
                    f"Route {route} is assigned to both "
                    f"{seen_routes[normalized_route]} and {product.product_name}"
                )
            seen_routes[normalized_route] = product.product_name


def _require_required_metadata(fields: tuple[str, ...]) -> None:
    _require_non_empty_tuple(fields, "required_metadata_fields")
    missing = set(DEFAULT_REQUIRED_METADATA_FIELDS) - set(fields)
    if missing:
        raise ValueError(
            "required_metadata_fields missing required field(s): " + ", ".join(sorted(missing))
        )


def _require_non_empty_tuple(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    for value in values:
        _require_text(value, field_name)


def _require_allowed(value: str, field_name: str, allowed: set[str]) -> None:
    _require_text(value, field_name)
    if value not in allowed:
        raise ValueError(f"{field_name} has unsupported value: {value}")


def _normalize_required_text(value: str, field_name: str) -> str:
    return _require_text(value, field_name).upper()


def _require_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned
