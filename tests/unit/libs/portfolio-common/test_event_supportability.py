import pytest

from portfolio_common import events
from portfolio_common.event_supportability import (
    CONTROL_EXECUTION,
    CONTROL_PLANE_AND_POLICY,
    DATA_QUALITY_COVERAGE_REPORT,
    DOMAIN_STATE_EVENT,
    EVENT_FAMILY_DEFINITIONS,
    INGESTION_EVIDENCE_BUNDLE,
    RECONCILIATION_CONTROL_EVENT,
    RECONCILIATION_EVIDENCE_BUNDLE,
    SOURCE_INGESTION_EVENT,
    SUPPORTABILITY_SURFACE_DEFINITIONS,
    SUPPORTABILITY_RECOVERY_EVENT,
    EventFamilyDefinition,
    SupportabilitySurfaceDefinition,
    get_event_family_definition,
    validate_event_supportability_catalog,
)


def test_event_supportability_catalog_validates_against_existing_event_models() -> None:
    available_models = {
        name for name in dir(events) if name.endswith("Event") or name.endswith("EventModel")
    }

    validate_event_supportability_catalog(available_schema_models=available_models)


def test_source_ingestion_events_are_idempotent_and_auditable() -> None:
    ingestion_events = [
        definition
        for definition in EVENT_FAMILY_DEFINITIONS
        if definition.family == SOURCE_INGESTION_EVENT
    ]

    assert ingestion_events
    for definition in ingestion_events:
        assert definition.idempotency_required is True
        assert definition.correlation_required is True
        assert definition.schema_version_required is True
        assert INGESTION_EVIDENCE_BUNDLE in definition.supportability_evidence


def test_reconciliation_events_bind_to_reconciliation_evidence() -> None:
    reconciliation_events = [
        definition
        for definition in EVENT_FAMILY_DEFINITIONS
        if definition.family == RECONCILIATION_CONTROL_EVENT
    ]

    assert {event.event_type for event in reconciliation_events} == {
        "FinancialReconciliationRequested",
        "FinancialReconciliationCompleted",
        "PortfolioDayControlsEvaluated",
    }
    for definition in reconciliation_events:
        assert RECONCILIATION_EVIDENCE_BUNDLE in definition.supportability_evidence


def test_supportability_surfaces_are_operator_only_and_evidence_backed() -> None:
    evidence_bundles = {surface.evidence_bundle for surface in SUPPORTABILITY_SURFACE_DEFINITIONS}

    assert evidence_bundles == {
        INGESTION_EVIDENCE_BUNDLE,
        RECONCILIATION_EVIDENCE_BUNDLE,
        DATA_QUALITY_COVERAGE_REPORT,
    }
    for surface in SUPPORTABILITY_SURFACE_DEFINITIONS:
        assert surface.operator_only is True
        assert surface.diagnostics


def test_supportability_surfaces_use_canonical_route_family_values() -> None:
    surface_families = {surface.route_family for surface in SUPPORTABILITY_SURFACE_DEFINITIONS}

    assert surface_families == {CONTROL_PLANE_AND_POLICY, CONTROL_EXECUTION}


def test_get_event_family_definition_is_case_insensitive() -> None:
    definition = get_event_family_definition("financialreconciliationcompleted")

    assert definition.event_type == "FinancialReconciliationCompleted"
    assert definition.family == RECONCILIATION_CONTROL_EVENT


def test_runtime_outbox_events_are_cataloged_with_current_topics() -> None:
    expected_topics = {
        "RawTransactionPersisted": "transactions.persisted",
        "ProcessedTransactionPersisted": "transactions.cost.processed",
        "InstrumentUpserted": "instruments.received",
        "MarketPricePersisted": "market_prices.persisted",
        "DailyPositionSnapshotPersisted": "valuation.snapshot.persisted",
        "CashflowCalculated": "cashflows.calculated",
    }

    for event_type, topic in expected_topics.items():
        definition = get_event_family_definition(event_type)
        assert definition.family == DOMAIN_STATE_EVENT
        assert definition.topic == topic


def test_runtime_pipeline_events_are_cataloged_with_current_topics() -> None:
    expected_topics = {
        "TransactionProcessingCompleted": "transaction_processing.ready",
        "PortfolioDayReadyForValuation": "portfolio_security_day.valuation.ready",
        "ValuationDayCompleted": "portfolio_security_day.valuation.completed",
        "PositionTimeseriesDayCompleted": ("portfolio_security_day.position_timeseries.completed"),
        "PortfolioAggregationDayCompleted": "portfolio_day.aggregation.completed",
    }

    for event_type, topic in expected_topics.items():
        assert get_event_family_definition(event_type).topic == topic


def test_replay_event_is_cataloged_as_supportability_recovery() -> None:
    definition = get_event_family_definition("ReprocessTransactionReplay")

    assert definition.family == SUPPORTABILITY_RECOVERY_EVENT
    assert definition.topic == "transactions.cost.processed"
    assert INGESTION_EVIDENCE_BUNDLE in definition.supportability_evidence


def test_validation_rejects_event_without_schema_versioning() -> None:
    invalid = EventFamilyDefinition(
        event_type="InvalidEvent",
        schema_model="PortfolioEvent",
        family=SOURCE_INGESTION_EVENT,
        direction="inbound",
        aggregate_type="portfolio",
        topic="portfolio.invalid",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=False,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
    )

    with pytest.raises(ValueError, match="must require schema versioning"):
        validate_event_supportability_catalog((invalid,), ())


def test_validation_rejects_missing_schema_model_binding() -> None:
    invalid = EventFamilyDefinition(
        event_type="InvalidEvent",
        schema_model="MissingEvent",
        family=SOURCE_INGESTION_EVENT,
        direction="inbound",
        aggregate_type="portfolio",
        topic="portfolio.invalid",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
    )

    with pytest.raises(ValueError, match="references missing schema model"):
        validate_event_supportability_catalog(
            (invalid,),
            (),
            available_schema_models={"PortfolioEvent"},
        )


def test_validation_rejects_unknown_source_data_product_binding() -> None:
    invalid = EventFamilyDefinition(
        event_type="InvalidEvent",
        schema_model="PortfolioEvent",
        family=SOURCE_INGESTION_EVENT,
        direction="inbound",
        aggregate_type="portfolio",
        topic="portfolio.invalid",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("UnknownProduct",),
    )

    with pytest.raises(ValueError, match="references unknown source-data product"):
        validate_event_supportability_catalog((invalid,), ())


def test_validation_rejects_unknown_supportability_surface_route_family() -> None:
    invalid_surface = SupportabilitySurfaceDefinition(
        name="InvalidSurface",
        service_name="query_control_plane_service",
        route_family="control_plane_and_policy",
        operator_only=True,
        evidence_bundle=DATA_QUALITY_COVERAGE_REPORT,
        diagnostics=("lineage",),
    )

    with pytest.raises(ValueError, match="route_family has unsupported value"):
        validate_event_supportability_catalog((), (invalid_surface,))
