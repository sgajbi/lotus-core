# Application Port Capability Catalog

This catalog is the human-readable companion to
`docs/architecture/application-port-capability-catalog.json`.

## Purpose

Application ports are the typed capabilities that use cases require from infrastructure. They keep
application orchestration testable without concrete SQLAlchemy repositories, Kafka producers, helper
functions, database sessions, or runtime global providers.

## Package Convention

Service-local application ports live under:

```text
src/services/<service>/app/ports/
```

Shared cross-service ports live in the smallest shared bounded context with multiple demonstrated
application consumers, such as `src/libs/portfolio-common/portfolio_common/event_publisher.py` or
`src/libs/portfolio-common/portfolio_common/runtime_providers.py`. Reused domain records or adapters
do not by themselves justify a shared port.

Existing clock/ID provider ports that predate this convention may remain in dedicated provider
modules while cataloged as transitional `clock-id-provider` capabilities.

## Current Representative Capabilities

| Capability | Family | Port module | Representative consumers |
| --- | --- | --- | --- |
| `ingestion.job-store` | audit/idempotency store | `ingestion_service/app/ports/ingestion_workflow_stores.py` | `IngestionJobService`; SQLAlchemy adapter in `ingestion_service/app/infrastructure/workflow_stores.py` |
| `ingestion.replay-audit-store` | audit/idempotency store | `ingestion_service/app/ports/ingestion_workflow_stores.py` | `IngestionJobService`; SQLAlchemy adapter in `ingestion_service/app/infrastructure/workflow_stores.py` |
| `events.event-publisher` | event publisher | `portfolio_common/event_publisher.py` | ingestion publish workflow, valuation job publisher, aggregation job publisher |
| `aggregation.scheduler-runtime-ports` | scheduler runtime | `portfolio_aggregation_service/app/ports/aggregation_scheduler_ports.py` | `AggregationScheduler`; SQLAlchemy, Prometheus, and system-clock adapters in `portfolio_aggregation_service/app/infrastructure/aggregation_scheduler_adapters.py` |
| `aggregation.timeseries-market-data-reader` | repository reader | `portfolio_aggregation_service/app/ports/timeseries_market_data.py` | `PortfolioTimeseriesLogic`; SQLAlchemy adapter in `portfolio_aggregation_service/app/infrastructure/portfolio_aggregation_repository.py` |
| `qcp.portfolio-tax-lot-reader` | repository reader | `query_control_plane_service/app/ports/dpm_source_readiness.py` | `PortfolioTaxLotWindow:v1` resolver; SQLAlchemy adapter in `query_control_plane_service/app/infrastructure/dpm_portfolio_state_sources.py` |
| `query.unit-of-work` | unit of work | `query_service/app/ports/unit_of_work.py` | `SimulationService`; SQLAlchemy adapter in `query_service/app/infrastructure/unit_of_work.py` |
| `reconciliation.repository-port` | repository reader/writer | `financial_reconciliation_service/app/ports/reconciliation_repository_ports.py` | `ReconciliationService` |
| `runtime.provider-ports` | clock/ID provider | `portfolio_common/runtime_providers.py` | `ReconciliationService`, `CoreSnapshotService`, `SimulationService` |

## Enforcement

`make architecture-guard` runs `scripts/quality/application_port_catalog_guard.py`,
`scripts/quality/application_dependency_inversion_guard.py`,
`scripts/quality/infrastructure_adapter_layer_guard.py`, `scripts/quality/repository_transaction_boundary_guard.py`,
and the specific port-regression guards for ingestion stores, event publishing, repository
capability ports, and unit-of-work boundaries.

The catalog guard validates that:

1. each cataloged port module exists,
2. each listed port symbol is defined in its port module,
3. service-local repository, store, downstream-client, cache, and unit-of-work ports use the
   `app/ports` package convention,
4. listed adapter, consumer, standard, and guard files exist,
5. capability identifiers are unique.

The dependency-inversion guard protects representative port-enabled application modules from
reintroducing direct SQLAlchemy sessions, concrete repositories, concrete Kafka producer APIs, or
direct helper calls for capabilities that now have ports.

## Runtime Boundary

This catalog improves design-time modularity inside the existing `lotus-core` deployables. It does
not create a new runtime service boundary, database, queue, or deployment unit.
