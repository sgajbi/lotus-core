# Lotus Core Target Architecture (RFC 057)

This document codifies the target module boundaries for `lotus-core` as approved in RFC 057.

## System Role

`lotus-core` is the canonical source of portfolio and position state for the Lotus ecosystem.

It owns:

1. Ingestion of externally sourced portfolio/market/reference data.
2. Event-driven persistence and core financial calculations.
3. Time-series materialization.
4. API-first read/query contracts for downstream systems.
5. Simulation state and projected position/summary APIs.

It does not own:

1. Advanced risk/performance/concentration analytics.
2. Review/summary reporting composition.

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

## Query Read / Control-Plane Split

`lotus-core` intentionally keeps:

1. `query_service` as the canonical read engine
2. `query_control_plane_service` as the curated external contract and support façade

The placement rule for new endpoints is documented in:

- `docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md`

That note is normative for deciding whether a new API belongs in:

1. direct read-plane ownership
2. control-plane contract ownership

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
