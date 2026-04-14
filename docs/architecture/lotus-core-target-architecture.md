# Lotus Core Target Architecture (RFC 057)

This document codifies the target module boundaries for `lotus-core` as approved in RFC 057.

Platform RFC-0082 now governs the downstream-facing domain-authority and analytics-serving boundary:

- `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`

Platform RFC-0083 now governs the system-of-record target architecture:

- `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0083-lotus-core-system-of-record-target-architecture.md`

The current local contract-family inventory is:

- `docs/architecture/RFC-0082-contract-family-inventory.md`

The current local target-state gap analysis and implementation slice map is:

- `docs/architecture/RFC-0083-target-state-gap-analysis.md`

## System Role

`lotus-core` is the canonical source of portfolio and position state for the Lotus ecosystem.

It owns:

1. Ingestion of externally sourced portfolio/market/reference data.
2. Event-driven persistence and core financial calculations.
3. Time-series materialization.
4. API-first operational read contracts for downstream systems.
5. Governed analytics-input contracts that provide source data, lineage, paging/export semantics, benchmark/reference inputs, and policy context to downstream analytics authorities.
6. Simulation state and projected position/summary APIs.
7. Support, lineage, replay, reconciliation, and control-plane contracts for operational safety.

It does not own:

1. Advanced risk/performance/concentration analytics.
2. Review/summary reporting composition.
3. Product-facing analytics interpretation, attribution narrative, active-risk narrative, or advisory recommendation logic.

## Layering Model

Target layering:

1. `domain`
 - business models, invariants, and pure domain logic.
2. `application`
 - use cases and orchestration of domain behavior.
3. `adapters`
 - REST, Kafka, DB, file adapters and integration glue.
4. `services`
 - deployable process entrypoints that compose adapters + application.
5. `platform`
 - cross-cutting concerns (logging, tracing, metrics, health, policy).

Dependency direction:

1. `domain` <- `application` <- `adapters` <- `services`
2. `platform` is shared infra; it must not carry domain business logic.

## API-First Boundary

1. Downstream applications consume only public lotus-core APIs.
2. Direct downstream DB coupling is out of contract.
3. Operational diagnostics should be provided by support/lineage APIs.
4. Downstream-facing APIs must be classified under the RFC-0082 contract-family model before material expansion.
5. Analytics input contracts expose canonical source data and provenance, not downstream analytics conclusions.

## RFC-0082 Contract Families

`lotus-core` downstream-facing APIs are classified as:

1. Operational reads
 - canonical portfolio, position, transaction, instrument, price, FX, lookup, and reporting-oriented source-data queries.
2. Snapshot and simulation
 - governed state bundles, simulation session state, and projected state views.
3. Analytics inputs
 - deterministic input products for `lotus-performance`, `lotus-risk`, and reporting consumers.
4. Control-plane and policy
 - capabilities, policy, support, lineage, replay, ingestion-health, and operator diagnostics.
5. Write ingress
 - canonical source-data and adapter ingestion contracts.
6. Control execution
 - reconciliation and financial control run contracts.

The inventory document records current route placement, watchlist areas, and consumer mapping.

## Query Read / Control-Plane Split

`lotus-core` intentionally keeps:

1. `query_service` as the operational read plane and canonical read engine
2. `query_control_plane_service` as the governed analytics-input, snapshot/simulation, support, lineage, integration policy, capability, and export contract plane

The placement rule for new endpoints is documented in:

- `docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md`
- `docs/architecture/RFC-0082-contract-family-inventory.md`

That note is normative for deciding whether a new API belongs in:

1. direct read-plane ownership
2. control-plane contract ownership
3. analytics-input product ownership
4. snapshot/simulation ownership
5. support/lineage/policy ownership

## Ingestion Modes

`lotus-core` supports multi-modal ingestion:

1. REST ingestion.
2. Kafka/event ingestion.
3. File upload ingestion.

Mode policy:

1. Canonical enterprise flow: external upstream -> ingestion contracts -> Kafka -> persistence.
2. Upload/bundle flows are adapter paths and must be feature-flagged as non-canonical.
3. Adapter flags:
 - `LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED`
 - `LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED`

## Position Contract Direction

`positions` becomes the canonical position-level surface for core-derived metrics.
Parallel `positions-analytics` contracts are removed from lotus-core.
