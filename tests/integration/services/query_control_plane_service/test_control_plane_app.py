from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.query_control_plane_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio


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
    assert "/simulation-sessions/{session_id}" in paths
    assert "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries" in paths


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
    calculator_slos = schema["paths"]["/support/portfolios/{portfolio_id}/calculator-slos"]["get"]
    lineage = schema["paths"]["/lineage/portfolios/{portfolio_id}/securities/{security_id}"]["get"]

    overview_portfolio = next(
        parameter for parameter in overview["parameters"] if parameter["name"] == "portfolio_id"
    )
    assert overview_portfolio["description"] == "Portfolio identifier."

    stale_threshold = next(
        parameter
        for parameter in calculator_slos["parameters"]
        if parameter["name"] == "stale_threshold_minutes"
    )
    assert stale_threshold["description"].startswith("Threshold in minutes")

    not_found_example = overview["responses"]["404"]["content"]["application/json"]["example"]
    assert not_found_example["detail"] == "Portfolio with id PORT-OPS-001 not found"

    lineage_not_found = lineage["responses"]["404"]["content"]["application/json"]["example"]
    assert lineage_not_found["detail"] == (
        "Lineage for portfolio PORT-OPS-001 and security SEC-US-IBM not found"
    )

    components = schema["components"]["schemas"]
    calculator_slo = components["CalculatorSloResponse"]
    lineage_keys = components["LineageKeyListResponse"]
    support_jobs = components["SupportJobListResponse"]
    support_overview = components["SupportOverviewResponse"]

    assert calculator_slo["properties"]["valuation"]["description"] == (
        "Valuation calculator SLO snapshot for this portfolio."
    )
    assert lineage_keys["properties"]["items"]["description"] == "Current lineage key states."
    assert support_jobs["properties"]["items"]["description"] == (
        "Operational jobs for support workflows."
    )
    assert support_overview["properties"]["failed_valuation_jobs"]["description"] == (
        "Number of valuation jobs currently in FAILED terminal state."
    )
    assert support_overview["properties"]["oldest_pending_aggregation_date"]["description"] == (
        "Oldest aggregation date among pending/processing jobs for backlog analysis."
    )
    assert support_overview["properties"]["aggregation_backlog_age_days"]["description"].startswith(
        "Backlog age in days computed from oldest pending aggregation date"
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


async def test_openapi_describes_simulation_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    get_session = schema["paths"]["/simulation-sessions/{session_id}"]["get"]
    delete_change = schema["paths"]["/simulation-sessions/{session_id}/changes/{change_id}"][
        "delete"
    ]
    create_session = schema["components"]["schemas"]["SimulationSessionCreateRequest"]

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


async def test_openapi_describes_analytics_input_parameters_and_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    portfolio_inputs = schema["paths"][
        "/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries"
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
    assert invalid_request["detail"] == "Either window or period must be provided."

    job_id_param = next(
        parameter for parameter in export_result["parameters"] if parameter["name"] == "job_id"
    )
    assert job_id_param["description"] == "Durable analytics export job identifier."

    incomplete_export = export_result["responses"]["422"]["content"]["application/json"]["example"]
    assert incomplete_export["detail"] == "Analytics export job JOB-AN-0001 is not complete."

    components = schema["components"]["schemas"]
    page_metadata = components["PageMetadata"]
    export_result_schema = components["AnalyticsExportJsonResultResponse"]

    assert page_metadata["properties"]["next_page_token"]["description"] == (
        "Opaque continuation token for the next page, null when no additional pages remain."
    )
    assert export_result_schema["properties"]["data"]["description"] == (
        "Serialized observations or rows from the selected dataset."
    )


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

    blocked_example = core_snapshot["responses"]["403"]["content"]["application/json"]["example"]
    assert blocked_example["detail"] == "SNAPSHOT_SECTIONS_BLOCKED_BY_POLICY: positions_projected"

    invalid_enrichment = enrichment_bulk["responses"]["400"]["content"]["application/json"][
        "example"
    ]
    assert invalid_enrichment["detail"] == "security_ids must contain at least one identifier"

    components = schema["components"]["schemas"]
    policy_response = components["EffectiveIntegrationPolicyResponse"]
    enrichment_request = components["InstrumentEnrichmentBulkRequest"]
    core_snapshot_governance = components["CoreSnapshotGovernanceMetadata"]
    core_snapshot_freshness = components["CoreSnapshotFreshnessMetadata"]
    core_snapshot_sections = components["CoreSnapshotSections"]

    assert policy_response["properties"]["policy_provenance"]["description"] == (
        "Policy lineage metadata showing how the effective policy was resolved."
    )
    assert enrichment_request["properties"]["security_ids"]["description"] == (
        "Canonical Lotus security identifiers to enrich in one deterministic batch."
    )
    assert core_snapshot_governance["properties"]["requested_sections"]["examples"] == [
        ["positions_baseline", "positions_projected", "positions_delta"]
    ]
    assert core_snapshot_freshness["properties"]["snapshot_timestamp"]["description"] == (
        "UTC timestamp of the resolved baseline snapshot when one exists."
    )
    assert core_snapshot_sections["properties"]["positions_delta"]["description"] == (
        "Per-security baseline versus projected deltas."
    )


async def test_openapi_describes_benchmark_reference_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    benchmark_assignment = schema["paths"][
        "/integration/portfolios/{portfolio_id}/benchmark-assignment"
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

    portfolio_param = next(
        parameter
        for parameter in benchmark_assignment["parameters"]
        if parameter["name"] == "portfolio_id"
    )
    assert portfolio_param["description"] == (
        "Portfolio identifier whose effective benchmark assignment is requested."
    )

    assignment_not_found = benchmark_assignment["responses"]["404"]["content"]["application/json"][
        "example"
    ]
    assert assignment_not_found["detail"] == (
        "No effective benchmark assignment found for portfolio and as_of_date."
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
    benchmark_market_series_response = components["BenchmarkMarketSeriesResponse"]
    risk_free_series_response = components["RiskFreeSeriesResponse"]
    coverage_response = components["CoverageResponse"]
    classification_taxonomy_response = components["ClassificationTaxonomyResponse"]

    assert benchmark_catalog["properties"]["records"]["description"] == (
        "Benchmark definition records effective for the requested date."
    )
    assert benchmark_market_series_response["properties"]["quality_status_summary"]["examples"] == [
        {"accepted": 31, "estimated": 2}
    ]
    assert risk_free_series_response["properties"]["lineage"]["examples"] == [
        {"contract_version": "rfc_062_v1", "source_system": "lotus-core"}
    ]
    assert coverage_response["properties"]["missing_dates_count"]["examples"] == [2]
    assert classification_taxonomy_response["properties"]["records"]["description"] == (
        "Classification taxonomy entries effective on the requested date."
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

    components = schema["components"]["schemas"]
    feature_capability = components["FeatureCapability"]
    workflow_capability = components["WorkflowCapability"]

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
