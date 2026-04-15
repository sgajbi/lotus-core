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


def test_cataloged_event_models_accept_governed_outbox_envelope_metadata() -> None:
    sample_payloads_by_schema_model = {
        "PortfolioEvent": {
            "portfolio_id": "P1",
            "base_currency": "USD",
            "open_date": "2026-01-01",
            "risk_exposure": "balanced",
            "investment_time_horizon": "long_term",
            "portfolio_type": "discretionary",
            "booking_center_code": "SG",
            "client_id": "C1",
            "status": "ACTIVE",
        },
        "TransactionEvent": {
            "transaction_id": "T1",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2026-04-10T00:00:00Z",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "100",
            "gross_transaction_amount": "1000",
            "trade_currency": "USD",
            "currency": "USD",
        },
        "MarketPricePersistedEvent": {
            "security_id": "S1",
            "price_date": "2026-04-10",
            "price": "101.25",
            "currency": "USD",
        },
        "InstrumentEvent": {
            "security_id": "S1",
            "name": "Instrument One",
            "isin": "US0000000001",
            "currency": "USD",
            "product_type": "EQUITY",
        },
        "DailyPositionSnapshotPersistedEvent": {
            "id": 1,
            "portfolio_id": "P1",
            "security_id": "S1",
            "date": "2026-04-10",
            "epoch": 0,
        },
        "CashflowCalculatedEvent": {
            "cashflow_id": 1,
            "transaction_id": "T1",
            "portfolio_id": "P1",
            "security_id": "S1",
            "cashflow_date": "2026-04-10",
            "amount": "12.34",
            "currency": "USD",
            "classification": "DIVIDEND",
            "timing": "eod",
            "is_position_flow": True,
            "is_portfolio_flow": False,
            "calculation_type": "standard",
        },
        "TransactionProcessingCompletedEvent": {
            "transaction_id": "T1",
            "portfolio_id": "P1",
            "security_id": "S1",
            "business_date": "2026-04-10",
        },
        "PortfolioDayReadyForValuationEvent": {
            "portfolio_id": "P1",
            "security_id": "S1",
            "valuation_date": "2026-04-10",
        },
        "ValuationDayCompletedEvent": {
            "daily_position_snapshot_id": 1,
            "portfolio_id": "P1",
            "security_id": "S1",
            "valuation_date": "2026-04-10",
        },
        "PositionTimeseriesDayCompletedEvent": {
            "portfolio_id": "P1",
            "security_id": "S1",
            "timeseries_date": "2026-04-10",
        },
        "PortfolioAggregationDayCompletedEvent": {
            "portfolio_id": "P1",
            "aggregation_date": "2026-04-10",
        },
        "FinancialReconciliationRequestedEvent": {
            "portfolio_id": "P1",
            "business_date": "2026-04-10",
        },
        "FinancialReconciliationCompletedEvent": {
            "portfolio_id": "P1",
            "business_date": "2026-04-10",
            "outcome_status": "PASSED",
            "reconciliation_types": ["transaction_cashflow"],
        },
        "PortfolioDayControlsEvaluatedEvent": {
            "portfolio_id": "P1",
            "business_date": "2026-04-10",
            "status": "PASSED",
        },
    }

    for definition in EVENT_FAMILY_DEFINITIONS:
        model_cls = getattr(events, definition.schema_model)
        payload = {
            **sample_payloads_by_schema_model[definition.schema_model],
            "event_type": definition.event_type,
            "schema_version": "1.0.0",
            "correlation_id": "corr-123",
        }

        parsed = model_cls.model_validate(payload)

        assert model_cls.model_config["extra"] == "ignore"
        assert parsed is not None


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
