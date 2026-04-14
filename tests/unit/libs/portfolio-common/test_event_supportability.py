import pytest

from portfolio_common import events
from portfolio_common.event_supportability import (
    DATA_QUALITY_COVERAGE_REPORT,
    EVENT_FAMILY_DEFINITIONS,
    INGESTION_EVIDENCE_BUNDLE,
    RECONCILIATION_CONTROL_EVENT,
    RECONCILIATION_EVIDENCE_BUNDLE,
    SOURCE_INGESTION_EVENT,
    SUPPORTABILITY_SURFACE_DEFINITIONS,
    EventFamilyDefinition,
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


def test_get_event_family_definition_is_case_insensitive() -> None:
    definition = get_event_family_definition("financialreconciliationcompleted")

    assert definition.event_type == "FinancialReconciliationCompleted"
    assert definition.family == RECONCILIATION_CONTROL_EVENT


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
