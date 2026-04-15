"""RFC-0083 event family and supportability catalog helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from portfolio_common.source_data_products import (
    CONTROL_PLANE_AND_POLICY,
    SOURCE_DATA_PRODUCT_CATALOG,
)
from portfolio_common.source_data_security import get_source_data_security_profile


SOURCE_INGESTION_EVENT = "source_ingestion_event"
DOMAIN_STATE_EVENT = "domain_state_event"
PIPELINE_STAGE_EVENT = "pipeline_stage_event"
RECONCILIATION_CONTROL_EVENT = "reconciliation_control_event"
SUPPORTABILITY_RECOVERY_EVENT = "supportability_recovery_event"

CONTROL_EXECUTION = "Control Execution"

INBOUND_EVENT = "inbound"
OUTBOUND_EVENT = "outbound"
INTERNAL_EVENT = "internal"

INGESTION_EVIDENCE_BUNDLE = "IngestionEvidenceBundle"
RECONCILIATION_EVIDENCE_BUNDLE = "ReconciliationEvidenceBundle"
DATA_QUALITY_COVERAGE_REPORT = "DataQualityCoverageReport"


@dataclass(frozen=True)
class EventFamilyDefinition:
    event_type: str
    schema_model: str
    family: str
    direction: str
    aggregate_type: str
    topic: str
    producer_service: str
    consumer_services: tuple[str, ...]
    idempotency_required: bool
    correlation_required: bool
    schema_version_required: bool
    supportability_evidence: tuple[str, ...] = ()
    source_data_products: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportabilitySurfaceDefinition:
    name: str
    service_name: str
    route_family: str
    operator_only: bool
    evidence_bundle: str
    diagnostics: tuple[str, ...]
    replay_or_repair_capable: bool = False


@dataclass(frozen=True)
class DirectKafkaTopicDefinition:
    name: str
    topic: str
    semantic_type: str
    producer_service: str
    consumer_services: tuple[str, ...]
    payload_contract: str
    idempotency_header_supported: bool
    correlation_header_supported: bool
    supportability_evidence: tuple[str, ...] = ()
    source_data_products: tuple[str, ...] = ()


EVENT_FAMILY_DEFINITIONS: tuple[EventFamilyDefinition, ...] = (
    EventFamilyDefinition(
        event_type="PortfolioIngested",
        schema_model="PortfolioEvent",
        family=SOURCE_INGESTION_EVENT,
        direction=INBOUND_EVENT,
        aggregate_type="portfolio",
        topic="portfolio.ingested",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("PortfolioStateSnapshot",),
    ),
    EventFamilyDefinition(
        event_type="TransactionIngested",
        schema_model="TransactionEvent",
        family=SOURCE_INGESTION_EVENT,
        direction=INBOUND_EVENT,
        aggregate_type="transaction",
        topic="transaction.ingested",
        producer_service="ingestion_service",
        consumer_services=("persistence_service", "pipeline_orchestrator_service"),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
    EventFamilyDefinition(
        event_type="MarketPricePersisted",
        schema_model="MarketPricePersistedEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="market_price",
        topic="market_prices.persisted",
        producer_service="persistence_service",
        consumer_services=("valuation_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("MarketDataWindow",),
    ),
    EventFamilyDefinition(
        event_type="RawTransactionPersisted",
        schema_model="TransactionEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="raw_transaction",
        topic="transactions.persisted",
        producer_service="persistence_service",
        consumer_services=("cost_calculator_service", "cashflow_calculator_service"),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow",),
    ),
    EventFamilyDefinition(
        event_type="ProcessedTransactionPersisted",
        schema_model="TransactionEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="processed_transaction",
        topic="transactions.cost.processed",
        producer_service="cost_calculator_service",
        consumer_services=(
            "cashflow_calculator_service",
            "pipeline_orchestrator_service",
            "position_calculator_service",
        ),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
    EventFamilyDefinition(
        event_type="InstrumentUpserted",
        schema_model="InstrumentEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="instrument",
        topic="instruments.received",
        producer_service="cost_calculator_service",
        consumer_services=("persistence_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("InstrumentReferenceBundle",),
    ),
    EventFamilyDefinition(
        event_type="DailyPositionSnapshotPersisted",
        schema_model="DailyPositionSnapshotPersistedEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="daily_position_snapshot",
        topic="valuation.snapshot.persisted",
        producer_service="valuation_service",
        consumer_services=("position_timeseries_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        source_data_products=("HoldingsAsOf", "PositionTimeseriesInput"),
    ),
    EventFamilyDefinition(
        event_type="CashflowCalculated",
        schema_model="CashflowCalculatedEvent",
        family=DOMAIN_STATE_EVENT,
        direction=OUTBOUND_EVENT,
        aggregate_type="cashflow",
        topic="cashflows.calculated",
        producer_service="cashflow_calculator_service",
        consumer_services=("pipeline_orchestrator_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        source_data_products=("TransactionLedgerWindow",),
    ),
    EventFamilyDefinition(
        event_type="TransactionProcessingCompleted",
        schema_model="TransactionProcessingCompletedEvent",
        family=PIPELINE_STAGE_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="transaction_processing.ready",
        producer_service="pipeline_orchestrator_service",
        consumer_services=("valuation_scheduler_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("HoldingsAsOf", "TransactionLedgerWindow"),
    ),
    EventFamilyDefinition(
        event_type="PortfolioDayReadyForValuation",
        schema_model="PortfolioDayReadyForValuationEvent",
        family=PIPELINE_STAGE_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_security_day.valuation.ready",
        producer_service="pipeline_orchestrator_service",
        consumer_services=("valuation_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("HoldingsAsOf",),
    ),
    EventFamilyDefinition(
        event_type="ValuationDayCompleted",
        schema_model="ValuationDayCompletedEvent",
        family=PIPELINE_STAGE_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_security_day.valuation.completed",
        producer_service="valuation_service",
        consumer_services=("position_timeseries_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("HoldingsAsOf", "PositionTimeseriesInput"),
    ),
    EventFamilyDefinition(
        event_type="PositionTimeseriesDayCompleted",
        schema_model="PositionTimeseriesDayCompletedEvent",
        family=PIPELINE_STAGE_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_security_day.position_timeseries.completed",
        producer_service="position_timeseries_service",
        consumer_services=("portfolio_aggregation_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("PositionTimeseriesInput",),
    ),
    EventFamilyDefinition(
        event_type="PortfolioAggregationDayCompleted",
        schema_model="PortfolioAggregationDayCompletedEvent",
        family=PIPELINE_STAGE_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_day.aggregation.completed",
        producer_service="portfolio_aggregation_service",
        consumer_services=("pipeline_orchestrator_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("PortfolioTimeseriesInput",),
    ),
    EventFamilyDefinition(
        event_type="FinancialReconciliationRequested",
        schema_model="FinancialReconciliationRequestedEvent",
        family=RECONCILIATION_CONTROL_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_day.reconciliation.requested",
        producer_service="pipeline_orchestrator_service",
        consumer_services=("financial_reconciliation_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(RECONCILIATION_EVIDENCE_BUNDLE,),
        source_data_products=("ReconciliationEvidenceBundle",),
    ),
    EventFamilyDefinition(
        event_type="FinancialReconciliationCompleted",
        schema_model="FinancialReconciliationCompletedEvent",
        family=RECONCILIATION_CONTROL_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_day.reconciliation.completed",
        producer_service="financial_reconciliation_service",
        consumer_services=("pipeline_orchestrator_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(RECONCILIATION_EVIDENCE_BUNDLE,),
        source_data_products=("ReconciliationEvidenceBundle",),
    ),
    EventFamilyDefinition(
        event_type="PortfolioDayControlsEvaluated",
        schema_model="PortfolioDayControlsEvaluatedEvent",
        family=RECONCILIATION_CONTROL_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="portfolio_day",
        topic="portfolio_day.controls.evaluated",
        producer_service="pipeline_orchestrator_service",
        consumer_services=("query_control_plane_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(
            RECONCILIATION_EVIDENCE_BUNDLE,
            DATA_QUALITY_COVERAGE_REPORT,
        ),
        source_data_products=("DataQualityCoverageReport",),
    ),
    EventFamilyDefinition(
        event_type="ReprocessTransactionReplay",
        schema_model="TransactionEvent",
        family=SUPPORTABILITY_RECOVERY_EVENT,
        direction=INTERNAL_EVENT,
        aggregate_type="transaction",
        topic="transactions.cost.processed",
        producer_service="position_calculator_service",
        consumer_services=("cost_calculator_service",),
        idempotency_required=True,
        correlation_required=True,
        schema_version_required=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
)


DIRECT_KAFKA_TOPIC_DEFINITIONS: tuple[DirectKafkaTopicDefinition, ...] = (
    DirectKafkaTopicDefinition(
        name="RawPortfolioReceived",
        topic="portfolios.raw.received",
        semantic_type="source_ingestion_fact",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        payload_contract="PortfolioEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("PortfolioStateSnapshot",),
    ),
    DirectKafkaTopicDefinition(
        name="RawTransactionReceived",
        topic="transactions.raw.received",
        semantic_type="source_ingestion_fact",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        payload_contract="TransactionEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
    DirectKafkaTopicDefinition(
        name="InstrumentReceived",
        topic="instruments.received",
        semantic_type="mixed_source_and_derived_fact",
        producer_service="ingestion_service,cost_calculator_service",
        consumer_services=("persistence_service",),
        payload_contract="InstrumentEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("InstrumentReferenceBundle",),
    ),
    DirectKafkaTopicDefinition(
        name="RawMarketPriceReceived",
        topic="market_prices.raw.received",
        semantic_type="source_ingestion_fact",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        payload_contract="MarketPriceEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("MarketDataWindow",),
    ),
    DirectKafkaTopicDefinition(
        name="RawFxRateReceived",
        topic="fx_rates.raw.received",
        semantic_type="source_ingestion_fact",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        payload_contract="FxRateEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("MarketDataWindow",),
    ),
    DirectKafkaTopicDefinition(
        name="RawBusinessDateReceived",
        topic="business_dates.raw.received",
        semantic_type="source_ingestion_fact",
        producer_service="ingestion_service",
        consumer_services=("persistence_service",),
        payload_contract="BusinessDateEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
    ),
    DirectKafkaTopicDefinition(
        name="TransactionReprocessingRequested",
        topic="transactions.reprocessing.requested",
        semantic_type="supportability_recovery_command",
        producer_service="ingestion_service,event_replay_service",
        consumer_services=("cost_calculator_service",),
        payload_contract="transaction_id_command",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
    DirectKafkaTopicDefinition(
        name="TransactionReprocessingPersistedReplay",
        topic="transactions.persisted",
        semantic_type="supportability_recovery_fact_replay",
        producer_service="event_replay_service",
        consumer_services=("cost_calculator_service", "cashflow_calculator_service"),
        payload_contract="TransactionEvent",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(INGESTION_EVIDENCE_BUNDLE,),
        source_data_products=("TransactionLedgerWindow", "HoldingsAsOf"),
    ),
    DirectKafkaTopicDefinition(
        name="ValuationJobRequested",
        topic="valuation.job.requested",
        semantic_type="pipeline_command",
        producer_service="valuation_orchestrator_service",
        consumer_services=("valuation_service",),
        payload_contract="valuation_job_command",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("HoldingsAsOf",),
    ),
    DirectKafkaTopicDefinition(
        name="PortfolioAggregationJobRequested",
        topic="portfolio_day.aggregation.job.requested",
        semantic_type="pipeline_command",
        producer_service="portfolio_aggregation_service",
        consumer_services=("portfolio_aggregation_service",),
        payload_contract="portfolio_aggregation_job_command",
        idempotency_header_supported=True,
        correlation_header_supported=True,
        supportability_evidence=(DATA_QUALITY_COVERAGE_REPORT,),
        source_data_products=("PortfolioTimeseriesInput",),
    ),
)


SUPPORTABILITY_SURFACE_DEFINITIONS: tuple[SupportabilitySurfaceDefinition, ...] = (
    SupportabilitySurfaceDefinition(
        name="IngestionOperationsDiagnostics",
        service_name="event_replay_service",
        route_family=CONTROL_PLANE_AND_POLICY,
        operator_only=True,
        evidence_bundle=INGESTION_EVIDENCE_BUNDLE,
        diagnostics=(
            "ingestion_job_replayability",
            "consumer_lag",
            "operating_band",
            "capacity_saturation",
            "stalled_jobs",
            "idempotency",
        ),
        replay_or_repair_capable=True,
    ),
    SupportabilitySurfaceDefinition(
        name="ConsumerDlqReplay",
        service_name="event_replay_service",
        route_family=CONTROL_PLANE_AND_POLICY,
        operator_only=True,
        evidence_bundle=INGESTION_EVIDENCE_BUNDLE,
        diagnostics=("dlq_event_listing", "deterministic_replay_fingerprint", "replay_audit"),
        replay_or_repair_capable=True,
    ),
    SupportabilitySurfaceDefinition(
        name="CoreSupportLineage",
        service_name="query_control_plane_service",
        route_family=CONTROL_PLANE_AND_POLICY,
        operator_only=True,
        evidence_bundle=DATA_QUALITY_COVERAGE_REPORT,
        diagnostics=("lineage", "readiness", "valuation_jobs", "aggregation_jobs"),
    ),
    SupportabilitySurfaceDefinition(
        name="ReconciliationOperations",
        service_name="financial_reconciliation_service",
        route_family=CONTROL_EXECUTION,
        operator_only=True,
        evidence_bundle=RECONCILIATION_EVIDENCE_BUNDLE,
        diagnostics=("reconciliation_runs", "findings", "blocking_controls"),
        replay_or_repair_capable=False,
    ),
)


def get_event_family_definition(event_type: str) -> EventFamilyDefinition:
    requested = _normalize_required_text(event_type, "event_type")
    for definition in EVENT_FAMILY_DEFINITIONS:
        if definition.event_type.upper() == requested:
            return definition
    raise KeyError(f"Unknown event family definition: {event_type}")


def validate_event_supportability_catalog(
    event_definitions: tuple[EventFamilyDefinition, ...] = EVENT_FAMILY_DEFINITIONS,
    supportability_surfaces: tuple[
        SupportabilitySurfaceDefinition, ...
    ] = SUPPORTABILITY_SURFACE_DEFINITIONS,
    direct_kafka_topics: tuple[DirectKafkaTopicDefinition, ...] = DIRECT_KAFKA_TOPIC_DEFINITIONS,
    available_schema_models: Iterable[str] | None = None,
) -> None:
    supported_families = {
        SOURCE_INGESTION_EVENT,
        DOMAIN_STATE_EVENT,
        PIPELINE_STAGE_EVENT,
        RECONCILIATION_CONTROL_EVENT,
        SUPPORTABILITY_RECOVERY_EVENT,
    }
    supported_directions = {INBOUND_EVENT, OUTBOUND_EVENT, INTERNAL_EVENT}
    supported_surface_route_families = {CONTROL_PLANE_AND_POLICY, CONTROL_EXECUTION}
    supported_evidence = {
        INGESTION_EVIDENCE_BUNDLE,
        RECONCILIATION_EVIDENCE_BUNDLE,
        DATA_QUALITY_COVERAGE_REPORT,
    }
    source_data_product_names = {
        product.product_name.upper(): product.product_name
        for product in SOURCE_DATA_PRODUCT_CATALOG
    }
    available_models = (
        {
            _normalize_required_text(model, "available_schema_models")
            for model in available_schema_models
        }
        if available_schema_models is not None
        else None
    )

    event_names: set[str] = set()
    for definition in event_definitions:
        event_type = _normalize_required_text(definition.event_type, "event_type")
        if event_type in event_names:
            raise ValueError(f"Duplicate event family definition: {definition.event_type}")
        event_names.add(event_type)
        schema_model = _normalize_required_text(definition.schema_model, "schema_model")
        _require_allowed(definition.family, "family", supported_families)
        _require_allowed(definition.direction, "direction", supported_directions)
        _normalize_required_text(definition.aggregate_type, "aggregate_type")
        _normalize_required_text(definition.topic, "topic")
        _normalize_required_text(definition.producer_service, "producer_service")
        if not definition.consumer_services:
            raise ValueError(f"{definition.event_type} must define at least one consumer service")
        for consumer_service in definition.consumer_services:
            _normalize_required_text(consumer_service, "consumer_services")
        if not definition.idempotency_required:
            raise ValueError(f"{definition.event_type} must require idempotency")
        if not definition.correlation_required:
            raise ValueError(f"{definition.event_type} must require correlation")
        if not definition.schema_version_required:
            raise ValueError(f"{definition.event_type} must require schema versioning")
        if not definition.source_data_products and not definition.supportability_evidence:
            raise ValueError(
                f"{definition.event_type} must link to source-data products or evidence"
            )
        for evidence_bundle in definition.supportability_evidence:
            _require_allowed(evidence_bundle, "supportability_evidence", supported_evidence)
        for product_name in definition.source_data_products:
            normalized_product_name = _normalize_required_text(product_name, "source_data_products")
            if normalized_product_name not in source_data_product_names:
                raise ValueError(
                    f"{definition.event_type} references unknown source-data product: "
                    f"{product_name}"
                )
        if available_models is not None and schema_model not in available_models:
            raise ValueError(
                f"{definition.event_type} references missing schema model: "
                f"{definition.schema_model}"
            )

    surface_names: set[str] = set()
    for surface in supportability_surfaces:
        surface_name = _normalize_required_text(surface.name, "name")
        if surface_name in surface_names:
            raise ValueError(f"Duplicate supportability surface: {surface.name}")
        surface_names.add(surface_name)
        _normalize_required_text(surface.service_name, "service_name")
        _require_allowed(surface.route_family, "route_family", supported_surface_route_families)
        _require_allowed(surface.evidence_bundle, "evidence_bundle", supported_evidence)
        evidence_profile = get_source_data_security_profile(surface.evidence_bundle)
        if not evidence_profile.operator_only:
            raise ValueError(
                f"{surface.name} evidence bundle must use an operator-only security profile"
            )
        if not surface.operator_only:
            raise ValueError(f"{surface.name} must be operator-only")
        if not surface.diagnostics:
            raise ValueError(f"{surface.name} must define diagnostics")
        for diagnostic in surface.diagnostics:
            _normalize_required_text(diagnostic, "diagnostics")

    direct_topic_names: set[str] = set()
    for topic_definition in direct_kafka_topics:
        name = _normalize_required_text(topic_definition.name, "name")
        if name in direct_topic_names:
            raise ValueError(f"Duplicate direct Kafka topic definition: {topic_definition.name}")
        direct_topic_names.add(name)
        _normalize_required_text(topic_definition.topic, "topic")
        _normalize_required_text(topic_definition.semantic_type, "semantic_type")
        _normalize_required_text(topic_definition.producer_service, "producer_service")
        _normalize_required_text(topic_definition.payload_contract, "payload_contract")
        if not topic_definition.consumer_services:
            raise ValueError(f"{topic_definition.name} must define at least one consumer service")
        for consumer_service in topic_definition.consumer_services:
            _normalize_required_text(consumer_service, "consumer_services")
        if not topic_definition.idempotency_header_supported:
            raise ValueError(f"{topic_definition.name} must support idempotency headers")
        if not topic_definition.correlation_header_supported:
            raise ValueError(f"{topic_definition.name} must support correlation headers")
        if (
            not topic_definition.source_data_products
            and not topic_definition.supportability_evidence
        ):
            raise ValueError(
                f"{topic_definition.name} must link to source-data products or evidence"
            )
        for evidence_bundle in topic_definition.supportability_evidence:
            _require_allowed(evidence_bundle, "supportability_evidence", supported_evidence)
        for product_name in topic_definition.source_data_products:
            normalized_product_name = _normalize_required_text(product_name, "source_data_products")
            if normalized_product_name not in source_data_product_names:
                raise ValueError(
                    f"{topic_definition.name} references unknown source-data product: "
                    f"{product_name}"
                )
        if (
            available_models is not None
            and not topic_definition.payload_contract.endswith("_command")
            and _normalize_required_text(topic_definition.payload_contract, "payload_contract")
            not in available_models
        ):
            raise ValueError(
                f"{topic_definition.name} references missing payload contract: "
                f"{topic_definition.payload_contract}"
            )


def _require_allowed(value: str, field_name: str, allowed: set[str]) -> None:
    normalized = _normalize_required_text(value, field_name)
    if normalized not in {item.upper() for item in allowed}:
        raise ValueError(f"{field_name} has unsupported value: {value}")


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized
