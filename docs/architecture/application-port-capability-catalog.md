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

Shared cross-service ports live in the smallest shared library that owns the reusable contract, such
as `src/libs/portfolio-common/portfolio_common/event_publisher.py`.

Existing clock/ID provider ports that predate this convention may remain in dedicated provider
modules while cataloged as transitional `clock-id-provider` capabilities.

## Current Representative Capabilities

| Capability | Family | Port module | Representative consumers |
| --- | --- | --- | --- |
| `ingestion.job-store` | audit/idempotency store | `ingestion_service/app/ports/ingestion_workflow_stores.py` | `IngestionJobService` |
| `ingestion.replay-audit-store` | audit/idempotency store | `ingestion_service/app/ports/ingestion_workflow_stores.py` | `IngestionJobService` |
| `events.event-publisher` | event publisher | `portfolio_common/event_publisher.py` | ingestion publish workflow, valuation job publisher |
| `query.portfolio-tax-lot-reader` | repository reader | `query_service/app/ports/source_data_repository_ports.py` | `PortfolioTaxLotWindow:v1` resolver |
| `reconciliation.repository-port` | repository reader/writer | `financial_reconciliation_service/app/ports/reconciliation_repository_ports.py` | `ReconciliationService` |
| `reconciliation.runtime-providers` | clock/ID provider | `financial_reconciliation_service/app/services/runtime_providers.py` | `ReconciliationService` |

## Enforcement

`make architecture-guard` runs `scripts/application_port_catalog_guard.py`,
`scripts/application_dependency_inversion_guard.py`, and the specific port-regression guards for
ingestion stores, event publishing, and repository capability ports.

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
