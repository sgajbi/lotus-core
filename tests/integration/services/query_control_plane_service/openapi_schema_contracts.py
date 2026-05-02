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

DPM_MODEL_PORTFOLIO_TARGET_SCHEMA_ROOTS = {
    "ModelPortfolioTargetRequest",
    "ModelPortfolioTargetRow",
    "ModelPortfolioSupportability",
    "ModelPortfolioTargetResponse",
}

DPM_MANDATE_BINDING_SCHEMA_ROOTS = {
    "DiscretionaryMandateBindingRequest",
    "RebalanceBandContext",
    "DiscretionaryMandateBindingSupportability",
    "DiscretionaryMandateBindingResponse",
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

BENCHMARK_REFERENCE_CATALOG_SCHEMA_ROOTS = {
    "BenchmarkDefinitionRequest",
    "BenchmarkDefinitionResponse",
    "BenchmarkCatalogRequest",
    "BenchmarkCatalogResponse",
    "IndexCatalogRequest",
    "IndexDefinitionResponse",
    "IndexCatalogResponse",
    "IndexSeriesRequest",
    "IndexPriceSeriesResponse",
    "IndexReturnSeriesResponse",
    "BenchmarkReturnSeriesRequest",
    "BenchmarkReturnSeriesResponse",
}

READINESS_SUPPORT_SCHEMA_ROOTS = {
    "PortfolioReadinessReason",
    "PortfolioReadinessBucket",
    "MissingHistoricalFxDependencyRecord",
    "MissingHistoricalFxDependencySummary",
    "PortfolioReadinessResponse",
    "CalculatorSloBucket",
    "ReprocessingSloBucket",
    "CalculatorSloResponse",
    "PortfolioControlStageRecord",
    "PortfolioControlStageListResponse",
}

SUPPORT_OPERATIONS_SCHEMA_ROOTS = {
    "SupportOverviewResponse",
    "SupportJobRecord",
    "SupportJobListResponse",
    "AnalyticsExportJobRecord",
    "AnalyticsExportJobListResponse",
}


def collect_schema_refs(property_schema: dict[str, object]) -> set[str]:
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


def assert_schema_properties_are_documented_and_exampled(
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

            pending.extend(sorted(collect_schema_refs(property_schema) - visited))

            has_example_signal = any(
                key in property_schema
                for key in (
                    "example",
                    "examples",
                    "default",
                    "enum",
                    "$ref",
                    "allOf",
                    "anyOf",
                    "oneOf",
                )
            )
            if property_schema.get("type") != "array":
                assert has_example_signal, (
                    f"{schema_name}.{property_name} is missing an OpenAPI "
                    "example/default/enum signal"
                )
