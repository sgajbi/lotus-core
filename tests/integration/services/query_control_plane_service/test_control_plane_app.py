from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.source_data_products import (
    QUERY_CONTROL_PLANE_SERVICE,
    SOURCE_DATA_PRODUCT_CATALOG,
)
from portfolio_common.source_data_security import (
    get_source_data_security_profile,
    required_source_data_capability,
)

from src.services.query_control_plane_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio

SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS = {
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
}

ANALYTICS_INPUT_SCHEMA_ROOTS = {
    "PortfolioAnalyticsReferenceRequest",
    "PortfolioAnalyticsReferenceResponse",
    "PortfolioAnalyticsTimeseriesRequest",
    "PortfolioAnalyticsTimeseriesResponse",
    "PositionAnalyticsTimeseriesRequest",
    "PositionAnalyticsTimeseriesResponse",
}

BENCHMARK_ASSIGNMENT_SCHEMA_ROOTS = {
    "BenchmarkAssignmentRequest",
    "BenchmarkAssignmentResponse",
    "IntegrationPolicyContext",
}

BENCHMARK_SOURCE_SCHEMA_ROOTS = {
    "BenchmarkCompositionWindowRequest",
    "BenchmarkCompositionWindowResponse",
    "BenchmarkMarketSeriesRequest",
    "BenchmarkMarketSeriesResponse",
    "ReferencePageRequest",
    "ReferencePageMetadata",
}

RISK_FREE_SCHEMA_ROOTS = {
    "RiskFreeSeriesRequest",
    "RiskFreeSeriesResponse",
    "RiskFreeSeriesPoint",
    "CoverageRequest",
    "CoverageResponse",
}

CLASSIFICATION_TAXONOMY_SCHEMA_ROOTS = {
    "ClassificationTaxonomyRequest",
    "ClassificationTaxonomyEntry",
    "ClassificationTaxonomyResponse",
}

RECONCILIATION_EVIDENCE_SCHEMA_ROOTS = {
    "ReconciliationRunListResponse",
    "ReconciliationFindingListResponse",
}

INGESTION_EVIDENCE_SCHEMA_ROOTS = {
    "LineageResponse",
    "LineageKeyListResponse",
    "ReprocessingKeyListResponse",
    "ReprocessingJobListResponse",
}

RECONCILIATION_SUPPORT_SCHEMA_ROOTS = {
    "ReconciliationRunListResponse",
    "ReconciliationFindingListResponse",
}

CAPABILITIES_SCHEMA_ROOTS = {
    "IntegrationCapabilitiesResponse",
    "FeatureCapability",
    "WorkflowCapability",
}

SIMULATION_SCHEMA_ROOTS = {
    "SimulationSessionCreateRequest",
    "SimulationSessionRecord",
    "SimulationSessionResponse",
    "SimulationChangeInput",
    "SimulationChangeRecord",
    "SimulationChangesResponse",
    "ProjectedPositionRecord",
    "ProjectedPositionsResponse",
    "ProjectedSummaryResponse",
}

CORE_SNAPSHOT_SCHEMA_ROOTS = {
    "CoreSnapshotSimulationOptions",
    "CoreSnapshotRequestOptions",
    "CoreSnapshotRequest",
    "CoreSnapshotValuationContext",
    "CoreSnapshotSimulationMetadata",
    "CoreSnapshotPolicyProvenance",
    "CoreSnapshotGovernanceMetadata",
    "CoreSnapshotFreshnessMetadata",
    "CoreSnapshotPositionRecord",
    "CoreSnapshotDeltaRecord",
    "CoreSnapshotInstrumentEnrichmentRecord",
    "CoreSnapshotPortfolioTotals",
    "CoreSnapshotSections",
    "CoreSnapshotResponse",
}

INTEGRATION_POLICY_SCHEMA_ROOTS = {
    "PolicyProvenanceMetadata",
    "EffectiveIntegrationPolicyResponse",
}

INSTRUMENT_ENRICHMENT_SCHEMA_ROOTS = {
    "InstrumentEnrichmentBulkRequest",
    "InstrumentEnrichmentRecord",
    "InstrumentEnrichmentBulkResponse",
}


def _collect_schema_refs(property_schema: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    direct_ref = property_schema.get("$ref")
    if isinstance(direct_ref, str):
        refs.add(direct_ref.rsplit("/", maxsplit=1)[-1])

    items = property_schema.get("items")
    if isinstance(items, dict):
        item_ref = items.get("$ref")
        if isinstance(item_ref, str):
            refs.add(item_ref.rsplit("/", maxsplit=1)[-1])

    for composition_key in ("anyOf", "allOf", "oneOf"):
        variants = property_schema.get(composition_key, [])
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_ref = variant.get("$ref")
            if isinstance(variant_ref, str):
                refs.add(variant_ref.rsplit("/", maxsplit=1)[-1])

    return refs


def _assert_schema_properties_are_documented_and_exampled(
    schema: dict[str, object],
    root_names: set[str],
) -> None:
    components = schema["components"]["schemas"]
    pending = list(root_names)
    visited: set[str] = set()

    while pending:
        schema_name = pending.pop(0)
        if schema_name in visited:
            continue
        visited.add(schema_name)
        current_schema = components[schema_name]
        properties = current_schema.get("properties", {})

        for property_name, property_schema in properties.items():
            assert "description" in property_schema, (
                f"{schema_name}.{property_name} is missing an OpenAPI description"
            )

            pending.extend(sorted(_collect_schema_refs(property_schema) - visited))

            has_example_signal = any(
                key in property_schema
                for key in ("example", "examples", "default", "enum", "$ref", "allOf", "anyOf", "oneOf")
            )
            if property_schema.get("type") != "array":
                assert has_example_signal, (
                    f"{schema_name}.{property_name} is missing an OpenAPI example/default/enum signal"
                )


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_middleware_preserves_incoming_correlation_id(async_test_client):
    response = await async_test_client.get(
        "/openapi.json", headers={"X-Correlation-ID": "corr-123"}
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"


async def test_openapi_binds_query_control_plane_source_data_products(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.serving_plane != QUERY_CONTROL_PLANE_SERVICE:
            continue
        for route in product.current_routes:
            path_item = schema["paths"][route]
            operation = path_item.get("post") or path_item.get("get")
            assert operation is not None
            extension = operation["x-lotus-source-data-product"]
            assert extension["product_name"] == product.product_name
            assert extension["product_version"] == product.product_version
            assert extension["route_family"] == product.route_family
            assert extension["serving_plane"] == product.serving_plane
            assert extension["owner"] == product.owner
            assert extension["consumers"] == list(product.consumers)
            assert extension["current_routes"] == list(product.current_routes)
            security_extension = operation["x-lotus-source-data-security"]
            profile = get_source_data_security_profile(product.product_name)
            assert security_extension["product_name"] == product.product_name
            assert security_extension["tenant_required"] == profile.tenant_required
            assert security_extension["entitlement_required"] == profile.entitlement_required
            assert security_extension["access_classification"] == profile.access_classification
            assert (
                security_extension["sensitivity_classification"]
                == profile.sensitivity_classification
            )
            assert security_extension["audit_requirement"] == profile.audit_requirement
            assert security_extension["required_capability"] == required_source_data_capability(
                product.product_name
            )
            assert security_extension["operator_only"] == profile.operator_only


async def test_openapi_binds_query_control_plane_source_data_product_response_identity(
    async_test_client,
):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    components = schema["components"]["schemas"]
    for product in SOURCE_DATA_PRODUCT_CATALOG:
        if product.serving_plane != QUERY_CONTROL_PLANE_SERVICE:
            continue
        for route in product.current_routes:
            path_item = schema["paths"][route]
            operation = path_item.get("post") or path_item.get("get")
            response_schema_ref = operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]["$ref"]
            response_schema_name = response_schema_ref.rsplit("/", maxsplit=1)[-1]
            response_schema = components[response_schema_name]

            assert response_schema["properties"]["product_name"]["default"] == product.product_name
            assert (
                response_schema["properties"]["product_version"]["default"]
                == product.product_version
            )


async def test_middleware_generates_correlation_id_when_missing(async_test_client):
    with patch(
        "src.services.query_control_plane_service.app.main.generate_correlation_id",
        return_value="QCP-abc",
    ):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QCP-abc"


async def test_middleware_replaces_unset_lineage_headers(async_test_client):
    with patch(
        "src.services.query_control_plane_service.app.main.generate_correlation_id",
        side_effect=["QCP-abc", "REQ-abc"],
    ):
        response = await async_test_client.get(
            "/openapi.json",
            headers={
                "X-Correlation-ID": "<not-set>",
                "X-Request-Id": "",
                "X-Trace-Id": "<not-set>",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QCP-abc"
    assert response.headers["X-Request-Id"] == "REQ-abc"
    assert response.headers["X-Trace-Id"] not in ("", "<not-set>")


async def test_lifespan_logs_startup_and_shutdown():
    with patch("src.services.query_control_plane_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Query Control Plane Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Query Control Plane Service has shut down gracefully." in logged_messages


async def test_openapi_contains_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/integration/capabilities" in paths
    assert "/integration/portfolios/{portfolio_id}/core-snapshot" in paths
    assert "/support/portfolios/{portfolio_id}/overview" in paths
    assert "/support/portfolios/{portfolio_id}/readiness" in paths
    assert "/simulation-sessions/{session_id}" in paths
    analytics_input_routes = {
        "/integration/portfolios/{portfolio_id}/analytics/reference",
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
        "/integration/portfolios/{portfolio_id}/analytics/position-timeseries",
    }
    assert analytics_input_routes <= set(paths)
    for route in analytics_input_routes:
        assert set(paths[route]) == {"post"}
    portfolio_timeseries = paths[
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries"
    ]["post"]
    position_timeseries = paths[
        "/integration/portfolios/{portfolio_id}/analytics/position-timeseries"
    ]["post"]
    portfolio_reference = paths["/integration/portfolios/{portfolio_id}/analytics/reference"][
        "post"
    ]
    assert "lotus-performance and lotus-risk" in portfolio_timeseries["description"]
    assert "historical risk attribution" in position_timeseries["description"]
    assert "lotus-performance and lotus-risk" in portfolio_reference["description"]

    assert "/integration/portfolios/{portfolio_id}/timeseries" not in paths
    assert "/integration/positions/{portfolio_id}/timeseries" not in paths


async def test_openapi_excludes_core_read_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/portfolios/{portfolio_id}" not in paths
    assert "/portfolios/{portfolio_id}/positions" not in paths
    assert "/portfolios/{portfolio_id}/transactions" not in paths


async def test_openapi_describes_operations_support_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    overview = schema["paths"]["/support/portfolios/{portfolio_id}/overview"]["get"]
    readiness = schema["paths"]["/support/portfolios/{portfolio_id}/readiness"]["get"]
    calculator_slos = schema["paths"]["/support/portfolios/{portfolio_id}/calculator-slos"]["get"]
    lineage = schema["paths"]["/lineage/portfolios/{portfolio_id}/securities/{security_id}"]["get"]

    overview_portfolio = next(
        parameter for parameter in overview["parameters"] if parameter["name"] == "portfolio_id"
    )
    assert overview_portfolio["description"] == "Portfolio identifier."
    overview_stale_threshold = next(
        parameter
        for parameter in overview["parameters"]
        if parameter["name"] == "stale_threshold_minutes"
    )
    assert overview_stale_threshold["description"].startswith("Threshold in minutes")
    overview_failed_window = next(
        parameter
        for parameter in overview["parameters"]
        if parameter["name"] == "failed_window_hours"
    )
    assert overview_failed_window["description"].startswith("Window in hours")

    readiness_as_of_date = next(
        parameter for parameter in readiness["parameters"] if parameter["name"] == "as_of_date"
    )
    assert readiness_as_of_date["description"] == (
        "Optional as-of date in YYYY-MM-DD format used to scope booked-state readiness."
    )

    stale_threshold = next(
        parameter
        for parameter in calculator_slos["parameters"]
        if parameter["name"] == "stale_threshold_minutes"
    )
    assert stale_threshold["description"].startswith("Threshold in minutes")
    failed_window = next(
        parameter
        for parameter in calculator_slos["parameters"]
        if parameter["name"] == "failed_window_hours"
    )
    assert failed_window["description"].startswith("Window in hours")

    not_found_example = overview["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found_example["detail"] == "Portfolio with id PORT-OPS-001 not found"

    lineage_not_found = lineage["responses"]["404"]["content"]["application/json"]["example"]
    assert lineage_not_found["detail"] == (
        "Lineage for portfolio PORT-OPS-001 and security SEC-US-IBM not found"
    )
    lineage_response = schema["components"]["schemas"]["LineageResponse"]
    assert lineage_response["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this lineage snapshot was generated."
    )
    assert lineage_response["properties"]["has_artifact_gap"]["description"].startswith(
        "True when the current epoch shows missing or lagging downstream artifacts"
    )
    assert lineage_response["properties"]["operational_state"]["description"].startswith(
        "Derived operator-facing lineage state for this key"
    )
    assert lineage_response["properties"]["latest_valuation_job_id"]["description"] == (
        "Durable database identifier of the latest valuation job in the current epoch."
    )
    assert lineage_response["properties"]["latest_valuation_job_correlation_id"][
        "description"
    ].startswith("Durable correlation identifier of the latest valuation job")

    analytics_export_jobs = schema["paths"][
        "/support/portfolios/{portfolio_id}/analytics-export-jobs"
    ]["get"]
    reconciliation_runs = schema["paths"]["/support/portfolios/{portfolio_id}/reconciliation-runs"][
        "get"
    ]
    reconciliation_findings = schema["paths"][
        "/support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings"
    ]["get"]
    control_stages = schema["paths"]["/support/portfolios/{portfolio_id}/control-stages"]["get"]
    reprocessing_keys = schema["paths"]["/support/portfolios/{portfolio_id}/reprocessing-keys"][
        "get"
    ]
    reprocessing_jobs = schema["paths"]["/support/portfolios/{portfolio_id}/reprocessing-jobs"][
        "get"
    ]
    assert "not business calculations" in reconciliation_runs["description"]
    assert "not business calculations" in reconciliation_findings["description"]
    assert "not direct business-calculation inputs" in reprocessing_keys["description"]
    assert "not direct business-calculation inputs" in reprocessing_jobs["description"]
    assert "not a business-calculation contract" in lineage["description"]
    assert "not business-calculation inputs" in schema["paths"]["/lineage/portfolios/{portfolio_id}/keys"]["get"]["description"]
    analytics_export_status = next(
        parameter
        for parameter in analytics_export_jobs["parameters"]
        if parameter["name"] == "status_filter"
    )
    assert analytics_export_status["description"].startswith("Optional export job status filter")
    for path_item in (
        analytics_export_jobs,
        reprocessing_jobs,
        reprocessing_keys,
        schema["paths"]["/support/portfolios/{portfolio_id}/valuation-jobs"]["get"],
        schema["paths"]["/support/portfolios/{portfolio_id}/aggregation-jobs"]["get"],
    ):
        listing_stale_threshold = next(
            parameter
            for parameter in path_item["parameters"]
            if parameter["name"] == "stale_threshold_minutes"
        )
        assert listing_stale_threshold["description"].startswith("Threshold in minutes")
    valuation_job_id = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/valuation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "job_id"
    )
    control_stage_id = next(
        parameter for parameter in control_stages["parameters"] if parameter["name"] == "stage_id"
    )
    assert control_stage_id["description"] == "Optional durable control-stage row id filter."
    assert valuation_job_id["description"] == "Optional durable valuation job id filter."
    valuation_business_date = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/valuation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "business_date"
    )
    assert (
        valuation_business_date["description"]
        == "Optional valuation business date filter in YYYY-MM-DD format."
    )
    valuation_security_id = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/valuation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "security_id"
    )
    assert (
        valuation_security_id["description"]
        == "Optional security identifier filter for one valuation job stream."
    )
    valuation_correlation_id = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/valuation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "correlation_id"
    )
    assert (
        valuation_correlation_id["description"]
        == "Optional durable valuation correlation identifier filter."
    )
    aggregation_job_id = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/aggregation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "job_id"
    )
    assert aggregation_job_id["description"] == "Optional durable aggregation job id filter."
    aggregation_business_date = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/aggregation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "business_date"
    )
    assert (
        aggregation_business_date["description"]
        == "Optional aggregation business date filter in YYYY-MM-DD format."
    )
    aggregation_correlation_id = next(
        parameter
        for parameter in schema["paths"]["/support/portfolios/{portfolio_id}/aggregation-jobs"][
            "get"
        ]["parameters"]
        if parameter["name"] == "correlation_id"
    )
    assert (
        aggregation_correlation_id["description"]
        == "Optional durable aggregation correlation identifier filter."
    )

    analytics_export_job_id = next(
        parameter
        for parameter in analytics_export_jobs["parameters"]
        if parameter["name"] == "job_id"
    )
    analytics_export_request_fingerprint = next(
        parameter
        for parameter in analytics_export_jobs["parameters"]
        if parameter["name"] == "request_fingerprint"
    )
    assert (
        analytics_export_job_id["description"]
        == "Optional durable analytics export job identifier filter."
    )
    assert (
        analytics_export_request_fingerprint["description"]
        == "Optional analytics export request fingerprint filter."
    )
    replay_job_id = next(
        parameter for parameter in reprocessing_jobs["parameters"] if parameter["name"] == "job_id"
    )
    assert replay_job_id["description"] == "Optional durable replay job id filter."
    replay_correlation_id = next(
        parameter
        for parameter in reprocessing_jobs["parameters"]
        if parameter["name"] == "correlation_id"
    )
    assert (
        replay_correlation_id["description"]
        == "Optional durable replay correlation identifier filter."
    )
    analytics_export_not_found = analytics_export_jobs["responses"]["404"]["content"][
        "application/json"
    ]["example"]
    assert analytics_export_not_found["detail"] == "Portfolio with id PORT-OPS-001 not found"
    assert reprocessing_jobs["summary"] == "List durable replay jobs for support workflows"
    reprocessing_jobs_status = next(
        parameter
        for parameter in reprocessing_jobs["parameters"]
        if parameter["name"] == "status_filter"
    )
    status_filter_example = (
        reprocessing_jobs_status.get("schema", {})
        .get("examples", {})
        .get("processing", {})
        .get("value")
        or reprocessing_jobs_status.get("examples", {}).get("processing", {}).get("value")
        or reprocessing_jobs_status.get("example")
        or reprocessing_jobs_status.get("schema", {}).get("example")
    )
    assert status_filter_example == "PROCESSING"
    reconciliation_correlation_id = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "correlation_id"
    )
    assert (
        reconciliation_correlation_id["description"]
        == "Optional durable reconciliation correlation identifier filter."
    )

    components = schema["components"]["schemas"]
    calculator_slo = components["CalculatorSloResponse"]
    lineage_keys = components["LineageKeyListResponse"]
    reprocessing_jobs_schema = components["ReprocessingJobListResponse"]
    support_jobs = components["SupportJobListResponse"]
    support_overview = components["SupportOverviewResponse"]
    readiness_response = components["PortfolioReadinessResponse"]
    analytics_export_jobs_schema = components["AnalyticsExportJobListResponse"]
    analytics_export_job_record = components["AnalyticsExportJobRecord"]

    assert calculator_slo["properties"]["valuation"]["description"] == (
        "Valuation calculator SLO snapshot for this portfolio."
    )
    assert lineage_keys["properties"]["items"]["description"] == "Current lineage key states."
    assert lineage_keys["properties"]["product_name"]["default"] == "IngestionEvidenceBundle"
    assert lineage_keys["properties"]["generated_at"]["description"] == (
        "UTC timestamp when this source-data product response was generated."
    )
    assert lineage_keys["properties"]["as_of_date"]["description"] == (
        "Business as-of date used to resolve this source-data product."
    )
    assert lineage_keys["properties"]["latest_evidence_timestamp"]["description"] == (
        "Latest linked evidence timestamp available for this product scope."
    )
    assert reprocessing_jobs_schema["properties"]["product_name"]["default"] == (
        "IngestionEvidenceBundle"
    )
    assert reprocessing_jobs_schema["properties"]["product_version"]["default"] == "v1"
    assert reprocessing_jobs_schema["properties"]["generated_at"]["description"] == (
        "UTC timestamp when this source-data product response was generated."
    )
    assert "product_name" not in support_jobs["properties"]
    assert support_jobs["properties"]["items"]["description"] == (
        "Operational jobs for support workflows."
    )
    assert support_jobs["properties"]["stale_threshold_minutes"]["description"] == (
        "Threshold in minutes used to classify stale support rows in this listing."
    )
    assert support_jobs["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this support job listing snapshot was generated."
    )
    support_job_record = components["SupportJobRecord"]
    assert support_job_record["properties"]["job_id"]["description"] == (
        "Durable database identifier for this job row."
    )
    assert support_job_record["properties"]["updated_at"]["description"] == (
        "UTC timestamp of the most recent durable lifecycle update for the job."
    )
    assert support_job_record["properties"]["is_retrying"]["description"].startswith(
        "True when the durable job has already consumed at least one retry attempt"
    )
    assert support_job_record["properties"]["correlation_id"]["description"].startswith(
        "Durable correlation identifier captured when the job was created"
    )
    assert support_job_record["properties"]["created_at"]["description"] == (
        "UTC timestamp when the durable job row was first created."
    )
    assert support_job_record["properties"]["is_stale_processing"]["description"].startswith(
        "True when the job is in PROCESSING state"
    )
    assert support_job_record["properties"]["is_terminal_failure"]["description"] == (
        "True when the durable job is in FAILED terminal state."
    )
    assert support_job_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing lifecycle state used for support triage ordering."
    )
    assert support_overview["properties"]["failed_valuation_jobs"]["description"] == (
        "Number of valuation jobs currently in FAILED terminal state."
    )
    assert readiness_response["properties"]["holdings"]["description"] == (
        "Holdings/snapshot coverage readiness for the portfolio."
    )
    assert readiness_response["properties"]["pricing"]["description"] == (
        "Pricing and valuation coverage readiness for the portfolio."
    )
    assert readiness_response["properties"]["missing_historical_fx_dependencies"][
        "description"
    ].startswith("Source-owned summary of cross-currency transactions blocked")
    assert support_overview["properties"]["controls_stage_id"]["description"].startswith(
        "Durable database identifier of the latest portfolio-day financial reconciliation"
    )
    assert support_overview["properties"]["controls_last_source_event_type"][
        "description"
    ].startswith("Most recent durable source event type recorded on the latest")
    assert support_overview["properties"]["controls_created_at"]["description"].startswith(
        "UTC timestamp when the latest portfolio-day financial reconciliation control"
    )
    assert support_overview["properties"]["controls_ready_emitted_at"]["description"].startswith(
        "UTC timestamp when the latest portfolio-day financial reconciliation control"
    )
    assert support_overview["properties"]["controls_failure_reason"]["description"].startswith(
        "Durable failure reason recorded on the latest portfolio-day financial"
    )
    assert support_overview["properties"]["controls_latest_reconciliation_run_id"][
        "description"
    ].startswith("Durable reconciliation run identifier for the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_type"][
        "description"
    ].startswith("Reconciliation type for the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_status"][
        "description"
    ].startswith("Durable lifecycle status for the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_correlation_id"][
        "description"
    ].startswith("Durable correlation identifier for the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_requested_by"][
        "description"
    ].startswith("Principal or subsystem that requested the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_dedupe_key"][
        "description"
    ].startswith("Stable deduplication key for the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_failure_reason"][
        "description"
    ].startswith("Failure reason recorded on the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_total_findings"][
        "description"
    ].startswith("Total durable finding count recorded on the latest reconciliation run")
    assert support_overview["properties"]["controls_latest_reconciliation_blocking_findings"][
        "description"
    ].startswith("Number of blocking reconciliation findings recorded on the latest")
    assert support_overview["properties"]["controls_latest_blocking_finding_id"][
        "description"
    ].startswith("Durable identifier of the most recent blocking reconciliation finding")
    assert support_overview["properties"]["controls_latest_blocking_finding_type"][
        "description"
    ].startswith("Finding type for the most recent blocking reconciliation finding")
    assert support_overview["properties"]["controls_latest_blocking_finding_security_id"][
        "description"
    ].startswith("Security identifier attached to the most recent blocking")
    assert support_overview["properties"]["controls_latest_blocking_finding_transaction_id"][
        "description"
    ].startswith("Transaction identifier attached to the most recent blocking")
    assert support_overview["properties"]["stale_threshold_minutes"]["description"] == (
        "Threshold in minutes used to classify stale in-flight portfolio processing."
    )
    assert support_overview["properties"]["failed_window_hours"]["description"] == (
        "Window in hours used to count recent failed jobs on the support overview."
    )
    assert support_overview["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this support overview snapshot was generated."
    )
    assert support_overview["properties"]["failed_valuation_jobs_within_window"][
        "description"
    ].startswith("Number of valuation jobs that moved to FAILED state within")
    assert support_overview["properties"]["failed_aggregation_jobs_within_window"][
        "description"
    ].startswith("Number of aggregation jobs that moved to FAILED state within")
    assert support_overview["properties"]["failed_analytics_export_jobs_within_window"][
        "description"
    ].startswith("Number of analytics export jobs that moved to FAILED state within")
    assert support_overview["properties"]["controls_last_updated_at"]["description"].startswith(
        "UTC timestamp of the most recent durable lifecycle update for the latest"
    )
    assert support_overview["properties"]["oldest_pending_aggregation_date"]["description"] == (
        "Oldest aggregation date among pending/processing jobs for backlog analysis."
    )
    assert support_overview["properties"]["aggregation_backlog_age_days"]["description"].startswith(
        "Backlog age in days computed from oldest pending aggregation date"
    )
    assert support_overview["properties"]["stale_reprocessing_keys"]["description"].startswith(
        "Number of REPROCESSING portfolio-security keys whose last update is older"
    )
    assert support_overview["properties"]["oldest_reprocessing_watermark_date"][
        "description"
    ].startswith("Oldest replay watermark date among portfolio-security keys")
    assert support_overview["properties"]["oldest_reprocessing_security_id"][
        "description"
    ].startswith("Security identifier for the oldest portfolio-security key")
    assert support_overview["properties"]["oldest_reprocessing_epoch"]["description"] == (
        "Current epoch of the oldest portfolio-security key currently marked REPROCESSING."
    )
    assert support_overview["properties"]["oldest_reprocessing_updated_at"][
        "description"
    ].startswith("UTC timestamp of the most recent durable update for the oldest")
    assert (
        support_overview["properties"]["oldest_pending_valuation_job_id"]["description"]
        == "Durable job id for the oldest open valuation job in the backlog."
    )
    assert (
        support_overview["properties"]["oldest_pending_valuation_security_id"]["description"]
        == "Security identifier for the oldest open valuation job in the backlog."
    )
    assert (
        support_overview["properties"]["oldest_pending_valuation_correlation_id"]["description"]
        == "Durable correlation identifier for the oldest open valuation job in the backlog."
    )
    assert (
        support_overview["properties"]["oldest_pending_aggregation_job_id"]["description"]
        == "Durable job id for the oldest open aggregation job in the backlog."
    )
    assert (
        support_overview["properties"]["oldest_pending_aggregation_correlation_id"]["description"]
        == "Durable correlation identifier for the oldest open aggregation job in the backlog."
    )
    assert (
        support_overview["properties"]["oldest_pending_analytics_export_job_id"]["description"]
        == "Durable job id for the oldest open analytics export job in the backlog."
    )
    assert support_overview["properties"]["oldest_pending_analytics_export_request_fingerprint"][
        "description"
    ].startswith("Request fingerprint for the oldest open analytics export job")
    assert support_overview["properties"]["reprocessing_backlog_age_days"][
        "description"
    ].startswith("Backlog age in days computed from oldest_reprocessing_watermark_date")
    assert calculator_slo["properties"]["failed_window_hours"]["description"] == (
        "Window in hours used to count recent failed jobs."
    )
    assert support_overview["properties"]["pending_analytics_export_jobs"]["description"] == (
        "Number of analytics export jobs currently waiting in ACCEPTED state."
    )
    assert support_overview["properties"]["failed_analytics_export_jobs"]["description"] == (
        "Number of analytics export jobs currently in FAILED terminal state."
    )
    assert support_overview["properties"]["analytics_export_backlog_age_minutes"][
        "description"
    ].startswith("Backlog age in minutes from the oldest waiting/running analytics export job")
    assert analytics_export_jobs_schema["properties"]["items"]["description"] == (
        "Durable analytics export jobs for support workflows."
    )
    assert (
        analytics_export_jobs_schema["properties"]["stale_threshold_minutes"]["description"]
        == "Threshold in minutes used to classify stale support rows in this listing."
    )
    assert analytics_export_jobs_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this analytics export listing snapshot was generated."
    )
    assert analytics_export_job_record["properties"]["request_fingerprint"][
        "description"
    ].startswith("Stable deduplication fingerprint for the export request")
    assert analytics_export_job_record["properties"]["dataset_type"]["description"] == (
        "Analytics dataset exported by the job."
    )
    assert analytics_export_job_record["properties"]["updated_at"]["description"] == (
        "UTC timestamp of the most recent durable lifecycle update for the export job."
    )
    assert analytics_export_job_record["properties"]["is_stale_running"]["description"].startswith(
        "True when the export job is in RUNNING state"
    )
    assert analytics_export_job_record["properties"]["is_terminal_failure"]["description"] == (
        "True when the export job is durably in FAILED terminal state."
    )
    assert analytics_export_job_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing lifecycle state used for support triage ordering."
    )
    assert analytics_export_job_record["properties"]["backlog_age_minutes"][
        "description"
    ].startswith("Age in minutes from created_at to the current UTC time")
    reprocessing_slo = components["ReprocessingSloBucket"]
    calculator_bucket = components["CalculatorSloBucket"]
    assert reprocessing_slo["properties"]["stale_reprocessing_keys"]["description"].startswith(
        "Number of REPROCESSING position keys whose last update is older"
    )
    assert (
        reprocessing_slo["properties"]["oldest_reprocessing_watermark_date"]["description"]
        == "Oldest watermark date among position keys currently in REPROCESSING state."
    )
    assert (
        reprocessing_slo["properties"]["oldest_reprocessing_security_id"]["description"]
        == "Security identifier for the oldest active reprocessing key."
    )
    assert reprocessing_slo["properties"]["oldest_reprocessing_epoch"]["description"] == (
        "Current epoch of the oldest active reprocessing key."
    )
    assert reprocessing_slo["properties"]["oldest_reprocessing_updated_at"]["description"] == (
        "UTC timestamp of the most recent durable update for the oldest active reprocessing key."
    )
    assert reprocessing_slo["properties"]["backlog_age_days"]["description"].startswith(
        "Age in days from oldest_reprocessing_watermark_date"
    )
    assert calculator_bucket["properties"]["oldest_open_job_id"]["description"] == (
        "Durable job id for the oldest open job contributing to this backlog."
    )
    assert (
        calculator_bucket["properties"]["oldest_open_job_correlation_id"]["description"]
        == "Durable correlation identifier for the oldest open job contributing to this backlog."
    )
    assert calculator_bucket["properties"]["failed_jobs_within_window"]["description"] == (
        "Count of jobs that moved to FAILED state within the configured failed-job window."
    )
    reconciliation_run_record = components["ReconciliationRunRecord"]
    assert reconciliation_run_record["properties"]["correlation_id"]["description"].startswith(
        "Durable correlation identifier captured for the reconciliation run"
    )
    reconciliation_type = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "reconciliation_type"
    )
    reconciliation_run_id = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "run_id"
    )
    assert (
        reconciliation_run_id["description"]
        == "Optional durable reconciliation run identifier filter."
    )
    reconciliation_requested_by = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "requested_by"
    )
    assert reconciliation_requested_by["description"] == "Optional reconciliation requester filter."
    reconciliation_dedupe_key = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "dedupe_key"
    )
    assert (
        reconciliation_dedupe_key["description"]
        == "Optional reconciliation deduplication key filter."
    )
    assert reconciliation_type["description"].startswith("Optional reconciliation type filter")
    reconciliation_status = next(
        parameter
        for parameter in reconciliation_runs["parameters"]
        if parameter["name"] == "status_filter"
    )
    assert reconciliation_status["description"].startswith("Optional run status filter")
    run_id_param = next(
        parameter
        for parameter in reconciliation_findings["parameters"]
        if parameter["name"] == "run_id"
    )
    assert run_id_param["description"] == "Reconciliation run identifier."
    finding_id_param = next(
        parameter
        for parameter in reconciliation_findings["parameters"]
        if parameter["name"] == "finding_id"
    )
    assert (
        finding_id_param["description"]
        == "Optional durable reconciliation finding identifier filter."
    )
    finding_security_param = next(
        parameter
        for parameter in reconciliation_findings["parameters"]
        if parameter["name"] == "security_id"
    )
    assert (
        finding_security_param["description"]
        == "Optional security identifier filter for reconciliation findings."
    )
    finding_transaction_param = next(
        parameter
        for parameter in reconciliation_findings["parameters"]
        if parameter["name"] == "transaction_id"
    )
    assert (
        finding_transaction_param["description"]
        == "Optional transaction identifier filter for reconciliation findings."
    )

    reconciliation_not_found = reconciliation_runs["responses"]["404"]["content"][
        "application/json"
    ]["example"]
    assert reconciliation_not_found["detail"] == "Portfolio with id PORT-OPS-001 not found"
    findings_not_found = reconciliation_findings["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert findings_not_found["detail"] == "Portfolio with id PORT-OPS-001 not found"
    control_stage_name = next(
        parameter for parameter in control_stages["parameters"] if parameter["name"] == "stage_name"
    )
    assert control_stage_name["description"].startswith("Optional control stage filter")
    control_stage_status = next(
        parameter
        for parameter in control_stages["parameters"]
        if parameter["name"] == "status_filter"
    )
    assert control_stage_status["description"].startswith("Optional control stage status filter")
    reprocessing_status = next(
        parameter
        for parameter in reprocessing_keys["parameters"]
        if parameter["name"] == "status_filter"
    )
    assert reprocessing_status["description"].startswith("Optional replay key status filter")
    reprocessing_security = next(
        parameter
        for parameter in reprocessing_keys["parameters"]
        if parameter["name"] == "security_id"
    )
    assert reprocessing_security["description"].startswith("Optional security identifier filter")
    reprocessing_watermark_date = next(
        parameter
        for parameter in reprocessing_keys["parameters"]
        if parameter["name"] == "watermark_date"
    )
    assert (
        reprocessing_watermark_date["description"]
        == "Optional replay watermark date filter in YYYY-MM-DD format."
    )
    control_stages_not_found = control_stages["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert control_stages_not_found["detail"] == "Portfolio with id PORT-OPS-001 not found"
    reprocessing_keys_not_found = reprocessing_keys["responses"]["404"]["content"][
        "application/json"
    ]["example"]
    assert reprocessing_keys_not_found["detail"] == "Portfolio with id PORT-OPS-001 not found"


async def test_openapi_describes_analytics_reference_contract(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]

    reference_post = schema["paths"]["/integration/portfolios/{portfolio_id}/analytics/reference"][
        "post"
    ]
    request_schema = schema["components"]["schemas"]["PortfolioAnalyticsReferenceRequest"]
    response_schema = schema["components"]["schemas"]["PortfolioAnalyticsReferenceResponse"]

    assert "current canonical portfolio reference fields" in reference_post["description"]
    assert (
        request_schema["properties"]["consumer_system"]["description"]
        == "Consumer system identifier for lineage and governance context."
    )
    assert (
        response_schema["properties"]["resolved_as_of_date"]["description"]
        == "Effective as-of anchor applied to this reference contract."
    )
    assert (
        response_schema["properties"]["reference_state_policy"]["default"]
        == "current_portfolio_reference_state"
    )
    assert response_schema["properties"]["product_name"]["default"] == "PortfolioAnalyticsReference"
    assert response_schema["properties"]["product_version"]["default"] == "v1"
    assert "latest_evidence_timestamp" in response_schema["properties"]
    assert "data_quality_status" in response_schema["properties"]
    assert (
        response_schema["properties"]["supported_grouping_dimensions"]["description"]
        == "Canonical grouping dimensions supported by analytics input contracts."
    )

    reconciliation_run_schema = components["ReconciliationRunListResponse"]
    reconciliation_run_record = components["ReconciliationRunRecord"]
    reconciliation_finding_schema = components["ReconciliationFindingListResponse"]
    reconciliation_finding_record = components["ReconciliationFindingRecord"]
    control_stage_schema = components["PortfolioControlStageListResponse"]
    control_stage_record = components["PortfolioControlStageRecord"]
    reprocessing_key_schema = components["ReprocessingKeyListResponse"]
    reprocessing_key_record = components["ReprocessingKeyRecord"]
    lineage_key_record = components["LineageKeyRecord"]
    lineage_key_schema = components["LineageKeyListResponse"]

    assert reconciliation_run_schema["properties"]["items"]["description"] == (
        "Durable reconciliation runs for support workflows."
    )
    assert reconciliation_run_schema["properties"]["product_name"]["default"] == (
        "ReconciliationEvidenceBundle"
    )
    assert reconciliation_run_schema["properties"]["product_version"]["default"] == "v1"
    assert reconciliation_run_schema["properties"]["generated_at"]["description"] == (
        "UTC timestamp when this source-data product response was generated."
    )
    assert reconciliation_run_schema["properties"]["as_of_date"]["description"] == (
        "Business as-of date used to resolve this source-data product."
    )
    assert reconciliation_run_schema["properties"]["latest_evidence_timestamp"]["description"] == (
        "Latest linked evidence timestamp available for this product scope."
    )
    assert reconciliation_run_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this reconciliation-run support snapshot was generated."
    )
    assert reconciliation_run_record["properties"]["requested_by"]["description"] == (
        "Principal or subsystem that requested the reconciliation run."
    )
    assert reconciliation_run_record["properties"]["dedupe_key"]["description"].startswith(
        "Stable deduplication key for the run"
    )
    assert reconciliation_run_record["properties"]["failure_reason"]["description"] == (
        "Failure reason when the reconciliation run reaches FAILED state."
    )
    assert reconciliation_run_record["properties"]["is_terminal_failure"]["description"] == (
        "True when the reconciliation run is durably in FAILED terminal state."
    )
    assert reconciliation_run_record["properties"]["is_blocking"]["description"].startswith(
        "True when the run status blocks downstream publication"
    )
    assert reconciliation_run_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing lifecycle state used for support triage ordering."
    )
    assert reconciliation_finding_schema["properties"]["items"]["description"] == (
        "Durable reconciliation findings for the requested run."
    )
    assert reconciliation_finding_schema["properties"]["product_name"]["default"] == (
        "ReconciliationEvidenceBundle"
    )
    assert reconciliation_finding_schema["properties"]["generated_at"]["description"] == (
        "UTC timestamp when this source-data product response was generated."
    )
    assert reconciliation_finding_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this reconciliation-finding support snapshot was generated."
    )
    assert reconciliation_finding_record["properties"]["detail"]["description"] == (
        "Structured detail describing the mismatch or control breach."
    )
    assert reconciliation_finding_record["properties"]["is_blocking"]["description"].startswith(
        "True when the finding represents a publication-blocking control breach"
    )
    assert reconciliation_finding_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing state for support triage of reconciliation findings."
    )
    assert control_stage_schema["properties"]["items"]["description"] == (
        "Durable portfolio-day control stage rows for support workflows."
    )
    assert control_stage_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this control-stage support snapshot was generated."
    )
    assert control_stage_record["properties"]["stage_id"]["description"] == (
        "Durable database identifier for this portfolio control stage row."
    )
    assert control_stage_record["properties"]["last_source_event_type"]["description"] == (
        "Last event type that updated the control stage row."
    )
    assert control_stage_record["properties"]["created_at"]["description"] == (
        "UTC timestamp when the durable control stage row was first created."
    )
    assert control_stage_record["properties"]["ready_emitted_at"]["description"] == (
        "UTC timestamp when the control stage emitted downstream readiness, if any."
    )
    assert control_stage_record["properties"]["is_blocking"]["description"] == (
        "True when the control stage blocks downstream publication or release decisions."
    )
    assert control_stage_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing lifecycle state used for support triage ordering."
    )
    assert reprocessing_key_schema["properties"]["items"]["description"] == (
        "Durable replay key rows for support workflows."
    )
    assert reprocessing_key_schema["properties"]["product_name"]["default"] == (
        "IngestionEvidenceBundle"
    )
    assert reprocessing_key_schema["properties"]["product_version"]["default"] == "v1"
    assert reprocessing_key_schema["properties"]["generated_at"]["description"] == (
        "UTC timestamp when this source-data product response was generated."
    )
    assert reprocessing_key_schema["properties"]["stale_threshold_minutes"]["description"] == (
        "Threshold in minutes used to classify stale support rows in this listing."
    )
    assert reprocessing_key_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this replay-key listing snapshot was generated."
    )
    assert lineage_key_schema["properties"]["generated_at_utc"]["description"] == (
        "UTC timestamp when this lineage key snapshot was generated."
    )
    assert reprocessing_key_record["properties"]["created_at"]["description"] == (
        "UTC timestamp when the durable replay key row was first created."
    )
    assert reprocessing_key_record["properties"]["updated_at"]["description"] == (
        "UTC timestamp of the most recent durable lifecycle update for the key."
    )
    assert reprocessing_key_record["properties"]["is_stale_reprocessing"]["description"].startswith(
        "True when the key is still marked REPROCESSING"
    )
    assert reprocessing_key_record["properties"]["operational_state"]["description"] == (
        "Derived operator-facing lifecycle state used for support triage ordering."
    )
    assert lineage_key_record["properties"]["latest_position_history_date"]["description"] == (
        "Latest position-history date for the current epoch of this key."
    )
    assert lineage_key_record["properties"]["latest_daily_snapshot_date"]["description"] == (
        "Latest daily snapshot date for the current epoch of this key."
    )
    assert lineage_key_record["properties"]["latest_valuation_job_status"]["description"] == (
        "Status of the latest valuation job recorded for the current epoch of this key."
    )
    assert lineage_key_record["properties"]["latest_valuation_job_id"]["description"] == (
        "Durable database identifier of the latest valuation job in the current epoch."
    )
    assert lineage_key_record["properties"]["latest_valuation_job_correlation_id"][
        "description"
    ].startswith("Durable correlation identifier of the latest valuation job")
    assert lineage_key_record["properties"]["has_artifact_gap"]["description"].startswith(
        "True when the current epoch shows missing or lagging downstream artifacts"
    )
    assert lineage_key_record["properties"]["operational_state"]["description"].startswith(
        "Derived operator-facing lineage state for this key"
    )


async def test_openapi_describes_simulation_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    create_route = schema["paths"]["/simulation-sessions"]["post"]
    get_session = schema["paths"]["/simulation-sessions/{session_id}"]["get"]
    projected_positions_route = schema["paths"]["/simulation-sessions/{session_id}/projected-positions"][
        "get"
    ]
    projected_summary_route = schema["paths"]["/simulation-sessions/{session_id}/projected-summary"][
        "get"
    ]
    delete_change = schema["paths"]["/simulation-sessions/{session_id}/changes/{change_id}"][
        "delete"
    ]
    create_session = schema["components"]["schemas"]["SimulationSessionCreateRequest"]

    assert "what-if simulation session" in create_route["description"]
    not_found_create = create_route["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found_create["detail"] == "Portfolio with id PORT-404 not found"

    session_param = next(
        parameter for parameter in get_session["parameters"] if parameter["name"] == "session_id"
    )
    assert session_param["description"] == "Simulation session identifier."

    not_found = get_session["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found["detail"] == "Simulation session SIM-20260310-0001 not found"

    change_id_param = next(
        parameter for parameter in delete_change["parameters"] if parameter["name"] == "change_id"
    )
    assert change_id_param["description"] == "Simulation change identifier."

    portfolio_id = create_session["properties"]["portfolio_id"]
    assert portfolio_id["description"] == "Portfolio identifier for the simulated scenario."

    components = schema["components"]["schemas"]
    session_response = components["SimulationSessionResponse"]
    changes_response = components["SimulationChangesResponse"]
    projected_positions = components["ProjectedPositionsResponse"]

    assert session_response["properties"]["session"]["description"] == (
        "Simulation session metadata."
    )
    assert changes_response["properties"]["changes"]["description"] == (
        "Current ordered set of simulation changes recorded for the session."
    )
    assert projected_positions["properties"]["positions"]["description"] == (
        "Projected positions after all simulation changes are applied."
    )
    assert "not for performance analytics" in projected_positions_route["description"]
    assert "not a recommendation" in projected_summary_route["description"]


async def test_openapi_simulation_schema_family_is_fully_documented(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, SIMULATION_SCHEMA_ROOTS)


async def test_openapi_describes_analytics_input_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    portfolio_inputs = schema["paths"][
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries"
    ]["post"]
    position_inputs = schema["paths"][
        "/integration/portfolios/{portfolio_id}/analytics/position-timeseries"
    ]["post"]
    export_result = schema["paths"][
        "/integration/exports/analytics-timeseries/jobs/{job_id}/result"
    ]["get"]

    portfolio_param = next(
        parameter
        for parameter in portfolio_inputs["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == (
        "Portfolio identifier for the requested analytics input contract."
    )

    invalid_request = portfolio_inputs["responses"]["400"]["content"]["application/json"]["example"]
    assert invalid_request["detail"] == "Exactly one of window or period must be provided."

    portfolio_product = portfolio_inputs["x-lotus-source-data-product"]
    assert portfolio_product["product_name"] == "PortfolioTimeseriesInput"
    assert portfolio_product["product_version"] == "v1"
    assert portfolio_product["route_family"] == "Analytics Input"
    assert portfolio_product["serving_plane"] == "query_control_plane_service"
    assert "lotus-performance" in portfolio_product["consumers"]
    assert "restatement_version" in portfolio_product["required_metadata_fields"]

    position_product = position_inputs["x-lotus-source-data-product"]
    assert position_product["product_name"] == "PositionTimeseriesInput"
    assert position_product["route_family"] == "Analytics Input"
    assert "lotus-risk" in position_product["consumers"]

    job_id_param = next(
        parameter for parameter in export_result["parameters"] if parameter["name"] == "job_id"
    )
    assert job_id_param["description"] == "Durable analytics export job identifier."

    incomplete_export = export_result["responses"]["422"]["content"]["application/json"]["example"]
    assert incomplete_export["detail"] == "Analytics export job JOB-AN-0001 is not complete."

    components = schema["components"]["schemas"]
    page_metadata = components["PageMetadata"]
    portfolio_response = components["PortfolioAnalyticsTimeseriesResponse"]
    position_response = components["PositionAnalyticsTimeseriesResponse"]
    portfolio_observation = components["PortfolioTimeseriesObservation"]
    position_request = components["PositionAnalyticsTimeseriesRequest"]
    position_row = components["PositionTimeseriesRow"]
    portfolio_diagnostics = components["PortfolioQualityDiagnostics"]
    diagnostics = components["QualityDiagnostics"]
    export_result_schema = components["AnalyticsExportJsonResultResponse"]
    export_job_schema = components["AnalyticsExportJobResponse"]

    assert page_metadata["properties"]["next_page_token"]["description"] == (
        "Opaque continuation token for the next page, null when no additional pages remain."
    )
    assert page_metadata["properties"]["sort_key"]["description"] == (
        "Stable ordering applied to rows for deterministic paging."
    )
    assert portfolio_response["properties"]["product_name"]["default"] == "PortfolioTimeseriesInput"
    assert portfolio_response["properties"]["product_version"]["default"] == "v1"
    assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(portfolio_response["properties"])
    assert position_response["properties"]["product_name"]["default"] == "PositionTimeseriesInput"
    assert position_response["properties"]["product_version"]["default"] == "v1"
    assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(position_response["properties"])
    assert portfolio_observation["properties"]["cash_flow_currency"]["description"] == (
        "Currency code applied to the observation cash_flows amounts; matches the "
        "effective reporting_currency."
    )
    assert position_request["properties"]["include_cash_flows"]["default"] is True
    assert position_row["properties"]["cash_flow_currency"]["description"] == (
        "Currency code applied to the row cash_flows amounts; normally matches position_currency."
    )
    cash_flow_observation = components["CashFlowObservation"]
    assert cash_flow_observation["properties"]["cash_flow_type"]["description"] == (
        "Canonical analytics cash flow type for downstream performance treatment."
    )
    assert cash_flow_observation["properties"]["flow_scope"]["description"] == (
        "High-level provenance scope that distinguishes external, internal, and operational flows."
    )
    assert cash_flow_observation["properties"]["source_classification"]["description"] == (
        "Underlying canonical cashflow classification that produced this "
        "analytics flow observation."
    )
    assert portfolio_diagnostics["properties"]["expected_business_dates_count"]["description"] == (
        "Number of expected business-calendar dates in the resolved window."
    )
    assert portfolio_diagnostics["properties"]["cash_flows_included"]["default"] is True
    assert diagnostics["properties"]["cash_flows_included"]["default"] is False
    assert export_result_schema["properties"]["data"]["description"] == (
        "Serialized observations or rows from the selected dataset."
    )
    assert export_job_schema["properties"]["lifecycle_mode"]["default"] == "inline_job_execution"
    assert export_job_schema["properties"]["disposition"]["description"].startswith(
        "How this response was produced"
    )
    assert export_job_schema["properties"]["result_available"]["description"] == (
        "True when a finalized result payload is available for retrieval."
    )
    assert export_result_schema["properties"]["request_fingerprint"]["description"] == (
        "Deterministic fingerprint for the request that produced this result."
    )
    assert export_result_schema["properties"]["result_row_count"]["description"] == (
        "Row count included in this export result payload."
    )


async def test_openapi_fully_documents_analytics_input_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, ANALYTICS_INPUT_SCHEMA_ROOTS)


async def test_openapi_describes_integration_policy_and_core_snapshot(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    effective_policy = schema["paths"]["/integration/policy/effective"]["get"]
    core_snapshot = schema["paths"]["/integration/portfolios/{portfolio_id}/core-snapshot"]["post"]
    enrichment_bulk = schema["paths"]["/integration/instruments/enrichment-bulk"]["post"]

    consumer_system = next(
        parameter
        for parameter in effective_policy["parameters"]
        if parameter["name"] == "consumer_system"
    )
    assert consumer_system["description"] == (
        "Downstream consumer system requesting policy resolution."
    )

    portfolio_param = next(
        parameter
        for parameter in core_snapshot["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == "Portfolio identifier for the snapshot request."
    assert not any(
        parameter["name"] == "consumer_system" for parameter in core_snapshot.get("parameters", [])
    )
    assert not any(
        parameter["name"] == "tenant_id" for parameter in core_snapshot.get("parameters", [])
    )

    blocked_example = core_snapshot["responses"]["403"]["content"]["application/json"]["example"]
    assert blocked_example["detail"] == "SNAPSHOT_SECTIONS_BLOCKED_BY_POLICY: positions_projected"

    invalid_enrichment = enrichment_bulk["responses"]["400"]["content"]["application/json"][
        "example"
    ]
    assert invalid_enrichment["detail"] == "security_ids must contain at least one identifier"

    components = schema["components"]["schemas"]
    policy_response = components["EffectiveIntegrationPolicyResponse"]
    enrichment_request = components["InstrumentEnrichmentBulkRequest"]
    enrichment_response = components["InstrumentEnrichmentBulkResponse"]
    core_snapshot_governance = components["CoreSnapshotGovernanceMetadata"]
    core_snapshot_freshness = components["CoreSnapshotFreshnessMetadata"]
    core_snapshot_request = components["CoreSnapshotRequest"]
    core_snapshot_response = components["CoreSnapshotResponse"]
    core_snapshot_sections = components["CoreSnapshotSections"]

    assert policy_response["properties"]["policy_provenance"]["description"] == (
        "Policy lineage metadata showing how the effective policy was resolved."
    )
    assert enrichment_request["properties"]["security_ids"]["description"] == (
        "Canonical Lotus security identifiers to enrich in one deterministic batch."
    )
    assert enrichment_response["properties"]["product_name"]["default"] == (
        "InstrumentReferenceBundle"
    )
    assert enrichment_response["properties"]["product_version"]["default"] == "v1"
    assert core_snapshot_governance["properties"]["requested_sections"]["examples"] == [
        ["positions_baseline", "positions_projected", "positions_delta"]
    ]
    assert core_snapshot_request["properties"]["consumer_system"]["description"] == (
        "Downstream consumer system requesting the core snapshot contract."
    )
    assert core_snapshot_request["properties"]["tenant_id"]["description"] == (
        "Tenant identifier used for governance and policy resolution."
    )
    assert core_snapshot_freshness["properties"]["snapshot_timestamp"]["description"] == (
        "UTC timestamp of the resolved baseline snapshot when one exists."
    )
    assert core_snapshot_freshness["properties"]["snapshot_epoch"]["description"] == (
        "Resolved baseline epoch when snapshot-backed state was used."
    )
    assert core_snapshot_freshness["properties"]["fallback_reason"]["description"] == (
        "Reason historical fallback was used instead of current snapshot-backed state."
    )
    assert core_snapshot_response["properties"]["contract_version"]["description"] == (
        "Contract version for the core snapshot response."
    )
    assert core_snapshot_response["properties"]["product_name"]["default"] == (
        "PortfolioStateSnapshot"
    )
    assert core_snapshot_response["properties"]["product_version"]["default"] == "v1"
    assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(core_snapshot_response["properties"])
    assert core_snapshot_response["properties"]["request_fingerprint"]["description"] == (
        "Deterministic fingerprint of the full core snapshot request contract."
    )
    assert "portfolio-state source data" in core_snapshot["description"]
    assert core_snapshot_request["properties"]["simulation"]["description"].startswith(
        "Simulation options required only when snapshot_mode=SIMULATION."
    )
    assert core_snapshot_request["properties"]["options"]["description"].startswith(
        "Request-level section behavior options controlling zero-quantity inclusion"
    )
    assert core_snapshot_response["properties"]["sections"]["description"].startswith(
        "Requested snapshot section payload."
    )
    assert core_snapshot_sections["properties"]["positions_delta"]["description"] == (
        "Per-security baseline versus projected deltas."
    )


async def test_openapi_fully_documents_core_snapshot_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, CORE_SNAPSHOT_SCHEMA_ROOTS)


async def test_openapi_fully_documents_policy_and_enrichment_schema_families(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(
        schema, INTEGRATION_POLICY_SCHEMA_ROOTS
    )
    _assert_schema_properties_are_documented_and_exampled(
        schema, INSTRUMENT_ENRICHMENT_SCHEMA_ROOTS
    )


async def test_openapi_describes_benchmark_reference_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    benchmark_assignment = schema["paths"][
        "/integration/portfolios/{portfolio_id}/benchmark-assignment"
    ]["post"]
    benchmark_composition_window = schema["paths"][
        "/integration/benchmarks/{benchmark_id}/composition-window"
    ]["post"]
    benchmark_definition = schema["paths"]["/integration/benchmarks/{benchmark_id}/definition"][
        "post"
    ]
    benchmark_market_series = schema["paths"][
        "/integration/benchmarks/{benchmark_id}/market-series"
    ]["post"]
    index_price_series = schema["paths"]["/integration/indices/{index_id}/price-series"]["post"]
    benchmark_coverage = schema["paths"]["/integration/benchmarks/{benchmark_id}/coverage"]["post"]
    risk_free_coverage = schema["paths"]["/integration/reference/risk-free-series/coverage"]["post"]
    risk_free_series = schema["paths"]["/integration/reference/risk-free-series"]["post"]
    classification_taxonomy = schema["paths"]["/integration/reference/classification-taxonomy"][
        "post"
    ]

    portfolio_param = next(
        parameter
        for parameter in benchmark_assignment["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == (
        "Portfolio identifier whose effective benchmark assignment is requested."
    )
    assert "lotus-performance, lotus-risk, and reporting" in benchmark_assignment["description"]
    assert "portfolio_id and as_of_date" in benchmark_assignment["description"]

    assignment_not_found = benchmark_assignment["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert assignment_not_found["detail"] == (
        "No effective benchmark assignment found for portfolio and as_of_date."
    )

    benchmark_id = next(
        parameter
        for parameter in benchmark_composition_window["parameters"]
        if parameter["name"] == "benchmark_id"
    )
    assert benchmark_id["description"] == (
        "Benchmark identifier for the requested composition window contract."
    )
    assert "without daily-expanding weights" in benchmark_composition_window["description"]
    assert "calculate benchmark returns across rebalance windows" in benchmark_composition_window[
        "description"
    ]

    composition_not_found = benchmark_composition_window["responses"]["404"]["content"][
        "application/json"
    ]["example"]
    assert composition_not_found["detail"] == (
        "No overlapping benchmark definition found for benchmark_id and requested window."
    )

    benchmark_id = next(
        parameter
        for parameter in benchmark_definition["parameters"]
        if parameter["name"] == "benchmark_id"
    )
    assert benchmark_id["description"] == (
        "Benchmark identifier for the requested benchmark definition."
    )

    definition_not_found = benchmark_definition["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert definition_not_found["detail"] == (
        "No effective benchmark definition found for benchmark_id and as_of_date."
    )

    market_series_param = next(
        parameter
        for parameter in benchmark_market_series["parameters"]
        if parameter["name"] == "benchmark_id"
    )
    assert market_series_param["description"] == (
        "Benchmark identifier for the requested market series input contract."
    )
    assert "lotus-performance and lotus-risk" in benchmark_market_series["description"]
    assert "benchmark-to-target FX context semantics" in benchmark_market_series["description"]
    assert "lotus-performance owns benchmark math" in benchmark_market_series["description"]
    assert "lotus-performance and lotus-risk" in risk_free_series["description"]
    assert "raw risk-free reference series" in risk_free_series["description"]
    assert "analytics readiness checks" in risk_free_coverage["description"]
    assert (
        "lotus-performance, lotus-risk, lotus-gateway, and lotus-advise"
        in (classification_taxonomy["description"])
    )
    assert "instead of local taxonomy drift" in classification_taxonomy["description"]
    assert "Missing labels remain absent rather than synthesized" in classification_taxonomy[
        "description"
    ]

    index_id = next(
        parameter
        for parameter in index_price_series["parameters"]
        if parameter["name"] == "index_id"
    )
    assert index_id["description"] == "Index identifier for the requested raw price series."

    coverage_param = next(
        parameter
        for parameter in benchmark_coverage["parameters"]
        if parameter["name"] == "benchmark_id"
    )
    assert coverage_param["description"] == (
        "Benchmark identifier for the requested coverage diagnostics."
    )

    currency_param = next(
        parameter
        for parameter in risk_free_coverage["parameters"]
        if parameter["name"] == "currency"
    )
    assert currency_param["description"] == "Risk-free series currency."

    components = schema["components"]["schemas"]
    benchmark_catalog = components["BenchmarkCatalogResponse"]
    benchmark_assignment_response = components["BenchmarkAssignmentResponse"]
    benchmark_composition_window_response = components["BenchmarkCompositionWindowResponse"]
    benchmark_market_series_response = components["BenchmarkMarketSeriesResponse"]
    index_price_series_response = components["IndexPriceSeriesResponse"]
    index_return_series_response = components["IndexReturnSeriesResponse"]
    risk_free_series_response = components["RiskFreeSeriesResponse"]
    coverage_response = components["CoverageResponse"]
    classification_taxonomy_response = components["ClassificationTaxonomyResponse"]
    benchmark_component_response = components["BenchmarkComponentResponse"]
    benchmark_assignment_request = components["BenchmarkAssignmentRequest"]

    assert benchmark_catalog["properties"]["records"]["description"] == (
        "Benchmark definition records effective for the requested date."
    )
    assert benchmark_composition_window_response["properties"]["segments"]["description"] == (
        "Ordered benchmark composition segments overlapping the requested window."
    )
    assert benchmark_component_response["properties"]["rebalance_event_id"]["description"] == (
        "Rebalance event identifier linking related composition changes."
    )
    assert benchmark_assignment_response["properties"]["product_name"]["default"] == (
        "BenchmarkAssignment"
    )
    assert benchmark_composition_window_response["properties"]["product_name"]["default"] == (
        "BenchmarkConstituentWindow"
    )
    assert benchmark_market_series_response["properties"]["product_name"]["default"] == (
        "MarketDataWindow"
    )
    assert index_price_series_response["properties"]["product_name"]["default"] == (
        "IndexSeriesWindow"
    )
    assert index_return_series_response["properties"]["product_name"]["default"] == (
        "IndexSeriesWindow"
    )
    assert risk_free_series_response["properties"]["product_name"]["default"] == (
        "RiskFreeSeriesWindow"
    )
    assert coverage_response["properties"]["product_name"]["default"] == (
        "DataQualityCoverageReport"
    )
    assert classification_taxonomy_response["properties"]["product_name"]["default"] == (
        "InstrumentReferenceBundle"
    )
    assert benchmark_assignment_response["properties"]["product_version"]["default"] == "v1"
    assert "does not change benchmark assignment selection" in (
        benchmark_assignment_request["properties"]["reporting_currency"]["description"]
    )
    assert "current implementation still resolves the effective assignment" in (
        benchmark_assignment_request["properties"]["policy_context"]["description"]
    )
    assert benchmark_assignment_response["properties"]["assignment_recorded_at"]["examples"] == [
        "2026-01-31T09:15:00Z"
    ]
    assert benchmark_assignment_response["properties"]["contract_version"]["examples"] == [
        "rfc_062_v1"
    ]
    source_data_product_reference_responses = [
        benchmark_assignment_response,
        benchmark_composition_window_response,
        benchmark_market_series_response,
        index_price_series_response,
        index_return_series_response,
        risk_free_series_response,
        coverage_response,
        classification_taxonomy_response,
    ]
    for response_schema in source_data_product_reference_responses:
        assert SOURCE_DATA_PRODUCT_RUNTIME_METADATA_FIELDS <= set(response_schema["properties"])
    assert benchmark_market_series_response["properties"]["quality_status_summary"]["examples"] == [
        {"accepted": 31, "estimated": 2}
    ]
    assert benchmark_market_series_response["properties"]["benchmark_currency"]["description"] == (
        "Benchmark currency resolved for the requested benchmark context."
    )
    assert benchmark_market_series_response["properties"]["request_fingerprint"]["description"] == (
        "Deterministic request fingerprint for the benchmark market-series scope."
    )
    assert benchmark_market_series_response["properties"]["page"]["description"] == (
        "Deterministic paging metadata for benchmark component series results."
    )
    assert (
        benchmark_market_series_response["properties"]["series_currency"]["description"]
        if "series_currency" in benchmark_market_series_response["properties"]
        else None
    ) is None
    component_series_ref = benchmark_market_series_response["properties"]["component_series"][
        "items"
    ]["$ref"]
    component_series_name = component_series_ref.rsplit("/", maxsplit=1)[-1]
    series_point_ref = components[component_series_name]["properties"]["points"]["items"]["$ref"]
    series_point_name = series_point_ref.rsplit("/", maxsplit=1)[-1]
    assert components[series_point_name]["properties"]["series_currency"]["description"] == (
        "Native component series currency for the returned price or return point."
    )
    assert components[series_point_name]["properties"]["fx_rate"]["description"] == (
        "Benchmark-currency to target-currency FX context rate when target currency "
        "is requested. This is not component-to-benchmark normalization."
    )
    assert benchmark_market_series_response["properties"]["normalization_policy"]["examples"] == [
        "native_component_series_downstream_normalization_required"
    ]
    assert benchmark_market_series_response["properties"]["normalization_status"]["examples"] == [
        "native_component_series_with_benchmark_to_target_fx_context"
    ]
    benchmark_market_series_request = components["BenchmarkMarketSeriesRequest"]
    assert benchmark_market_series_request["properties"]["page"]["description"] == (
        "Optional deterministic paging controls for large benchmark component universes."
    )
    assert benchmark_market_series_request["properties"]["frequency"]["description"] == (
        "Requested output frequency label. Currently only daily is supported."
    )
    assert risk_free_series_response["properties"]["lineage"]["examples"] == [
        {"contract_version": "rfc_062_v1", "source_system": "lotus-core"}
    ]
    assert (
        components["IndexReturnSeriesResponse"]["properties"]["request_fingerprint"]["description"]
        == "Deterministic request fingerprint for the raw index return series scope."
    )
    assert (
        components["BenchmarkReturnSeriesResponse"]["properties"]["request_fingerprint"][
            "description"
        ]
        == "Deterministic request fingerprint for the raw benchmark return series scope."
    )
    assert (
        risk_free_series_response["properties"]["request_fingerprint"]["description"]
        == "Deterministic request fingerprint for the raw risk-free series scope."
    )
    assert coverage_response["properties"]["missing_dates_count"]["examples"] == [2]
    assert coverage_response["properties"]["request_fingerprint"]["description"] == (
        "Deterministic request fingerprint for the coverage diagnostics scope."
    )
    assert classification_taxonomy_response["properties"]["records"]["description"] == (
        "Classification taxonomy entries effective on the requested date."
    )
    assert classification_taxonomy_response["properties"]["request_fingerprint"]["description"] == (
        "Deterministic request fingerprint for the taxonomy response scope."
    )
    assert classification_taxonomy_response["properties"]["taxonomy_version"]["examples"] == [
        "rfc_062_v1"
    ]
    reference_page_metadata = components["ReferencePageMetadata"]
    assert reference_page_metadata["properties"]["returned_component_count"]["description"] == (
        "Number of component series records returned in the current page."
    )
    assert reference_page_metadata["properties"]["request_scope_fingerprint"]["description"] == (
        "Deterministic fingerprint of the request scope bound to this page sequence."
    )


async def test_openapi_fully_documents_benchmark_assignment_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, BENCHMARK_ASSIGNMENT_SCHEMA_ROOTS)


async def test_openapi_fully_documents_benchmark_source_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, BENCHMARK_SOURCE_SCHEMA_ROOTS)


async def test_openapi_fully_documents_risk_free_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, RISK_FREE_SCHEMA_ROOTS)


async def test_openapi_fully_documents_classification_taxonomy_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(
        schema, CLASSIFICATION_TAXONOMY_SCHEMA_ROOTS
    )


async def test_openapi_fully_documents_reconciliation_evidence_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(
        schema, RECONCILIATION_EVIDENCE_SCHEMA_ROOTS
    )


async def test_openapi_fully_documents_ingestion_evidence_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, INGESTION_EVIDENCE_SCHEMA_ROOTS)


async def test_openapi_fully_documents_reconciliation_support_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(
        schema, RECONCILIATION_SUPPORT_SCHEMA_ROOTS
    )


async def test_openapi_describes_capabilities_query_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    capabilities = schema["paths"]["/integration/capabilities"]["get"]
    consumer_system = next(
        parameter
        for parameter in capabilities["parameters"]
        if parameter["name"] == "consumer_system"
    )
    tenant_id = next(
        parameter for parameter in capabilities["parameters"] if parameter["name"] == "tenant_id"
    )

    assert consumer_system["description"] == "Consumer requesting capability metadata."
    assert consumer_system["schema"]["default"] == "lotus-gateway"
    assert tenant_id["description"] == "Tenant or client identifier for policy resolution."
    assert tenant_id["schema"]["default"] == "default"
    assert "supported lotus-core integration paths" in capabilities["description"]
    assert "snake_case query parameters" in capabilities["description"]

    components = schema["components"]["schemas"]
    feature_capability = components["FeatureCapability"]
    workflow_capability = components["WorkflowCapability"]
    capabilities_response = components["IntegrationCapabilitiesResponse"]

    assert feature_capability["properties"]["key"]["description"] == "Canonical feature key."
    assert feature_capability["properties"]["owner_service"]["description"] == (
        "Owning service for the feature capability."
    )
    assert workflow_capability["properties"]["workflow_key"]["description"] == (
        "Workflow identifier."
    )
    assert workflow_capability["properties"]["required_features"]["description"] == (
        "Feature keys required for workflow execution."
    )
    assert capabilities_response["properties"]["consumer_system"]["description"] == (
        "Canonical consumer system receiving capabilities."
    )
    assert capabilities_response["properties"]["tenant_id"]["description"] == (
        "Tenant identifier used for capability policy resolution."
    )


async def test_openapi_fully_documents_capabilities_schema_family(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    _assert_schema_properties_are_documented_and_exampled(schema, CAPABILITIES_SCHEMA_ROOTS)
