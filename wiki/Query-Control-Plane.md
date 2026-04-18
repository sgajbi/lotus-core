# Query Control Plane

## Purpose

The query control plane is the governed downstream contract and supportability surface inside
`lotus-core`.

It exists alongside `query_service`, not in place of it. `query_service` owns canonical operational
read routes, while `query_control_plane_service` owns control-plane APIs for analytics inputs,
integration contracts, support, lineage, policy, simulation, and export workflows.

## What it handles

The current runtime centers on:

- analytics-input source-data products for downstream performance and risk consumers
- governed portfolio snapshot and integration contracts
- support, readiness, lineage, reconciliation, and reprocessing evidence routes
- integration policy and capability discovery
- deterministic simulation-session workflows
- analytics export job lifecycle for large-window retrieval

This makes it a contract and operations plane, not a generic duplicate of the read API.

## Runtime role

The service groups several related surfaces:

1. `operations`
   support overviews, readiness, lineage, reconciliation evidence, reprocessing and job-state views
2. `integration`
   policy-aware core snapshots, enrichment/reference contracts, benchmark and market/reference
   source-data products
3. `analytics_inputs`
   canonical portfolio and position analytics timeseries plus reference metadata and export jobs
4. `capabilities`
   tenant- and consumer-aware discovery of supported integration workflows
5. `simulation`
   deterministic what-if sessions and projected-state inspection
6. `advisory_simulation`
   governed canonical simulation execution contract for core source effects

The key design rule is that these APIs publish governed source state, support evidence, or control
policy. They do not own downstream analytics conclusions or advisory decisioning.

## Data and contract surfaces it owns

Primary contract areas include:

- `PortfolioStateSnapshot`
- `PortfolioTimeseriesInput`
- `PositionTimeseriesInput`
- `PortfolioAnalyticsReference`
- integration policy and capability diagnostics
- supportability, lineage, reconciliation, and reprocessing evidence bundles
- simulation session and projected-state contracts
- analytics export job state

These outputs feed:

- `lotus-gateway`
- `lotus-performance`
- `lotus-risk`
- `lotus-advise`
- `lotus-manage`
- operator and support tooling

## Why it matters

If the control plane is blurred or under-documented:

- downstream services can couple directly to the wrong tables or routes
- support and readiness state gets inferred indirectly instead of read from governed evidence routes
- simulation can drift toward advisory logic instead of staying deterministic and source-owned
- analytics-input and export consumers can adopt inconsistent contract shapes

That is why `query_control_plane_service` is a distinct service boundary rather than a convenience
router inside the operational read plane.

## Boundary rules

- `query_service` owns canonical operational read routes
- `query_control_plane_service` owns downstream source-data products and control-plane contracts
- the service may expose supportability and policy evidence, but it does not own business
  calculations that belong to calculators or downstream analytics services
- simulation routes must stay deterministic and source-owned, not recommendation-bearing

## Operational hints

Check this service when:

- a downstream consumer needs analytics-input or snapshot contracts
- a UI or operator flow needs readiness, lineage, reconciliation, or reprocessing evidence
- integration policy or capability posture needs to be inspected before calling a governed route
- large analytics windows need export-job retrieval instead of direct inline pagination
- what-if projected state is needed without mutating booked baseline state

Check beyond this service when:

- the need is a simple operational portfolio/transaction/position read that belongs in
  `query_service`
- the request is for downstream performance, risk, or advisory conclusions rather than core source
  state

## Related references

- [API Surface](API-Surface)
- [Support and Lineage](Support-and-Lineage)
- [System Data Flow](System-Data-Flow)
- [Financial Reconciliation](Financial-Reconciliation)
- [Event Replay Service](Event-Replay-Service)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
- [RFC-0083 Source-Data Product Catalog](../docs/architecture/RFC-0083-source-data-product-catalog.md)
