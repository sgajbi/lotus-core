# Integrations

## Primary integration relationships

- `lotus-gateway`
  workspace and product-facing composition over governed operational-read, snapshot, readiness, and
  source-data contracts
- `lotus-performance`
  canonical analytics-input, benchmark/reference, FX, and portfolio context sourcing
- `lotus-risk`
  canonical analytics-input, benchmark/reference, risk-free, and policy-aware snapshot sourcing
- `lotus-advise`
  stateful context reads, instrument and price support, and canonical advisory simulation execution
- `lotus-manage`
  management-side workflows that need core authority or future operator evidence adoption
- `lotus-report`
  reporting and evidence workflows that depend on governed core truth, even where current direct
  route adoption is intentionally narrow
- operator tooling and QA flows
  readiness, support, lineage, replay, and reconciliation investigation

## Main integration surfaces

- operational reads from `query_service`
- analytics-input, snapshot, policy, and support contracts from `query_control_plane_service`
- write-ingress contracts from `ingestion_service`
- replay and operations control-plane contracts from `event_replay_service`
- reconciliation control execution contracts

## Important rule

Downstream consumers should use the correct family surface rather than treating `lotus-core` as one
undifferentiated API.

That means:

- use `query_service` for canonical operational reads
- use `query_control_plane_service` for policy, snapshot, analytics-input, support, lineage, and
  simulation-oriented source contracts
- use `ingestion_service` for write ingress
- use `event_replay_service` and `financial_reconciliation_service` for control execution and
  operations recovery, not for front-office reads

## Adoption rule

Do not overstate current direct adoption from this page.

Some Lotus applications consume `lotus-core` directly, some consume through `lotus-gateway`, and
some have catalog-intended future adoption without a broad active route footprint today.

When route-specific adoption matters, use the RFC-0082 contract-family inventory and downstream
consumer audit instead of treating this page as a route-by-route source of truth.

## Reference

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0082 Downstream Endpoint Consumer And Test Coverage Audit](../docs/architecture/RFC-0082-downstream-endpoint-consumer-and-test-coverage-audit.md)
- [Architecture Index](../docs/architecture/README.md)
- [Query Service And Control Plane Boundary](../docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)
- [API Surface](API-Surface)

## Read Next

1. use [API Surface](API-Surface) when you need the grouped route families rather than the repo map,
2. use [System Data Flow](System-Data-Flow) when the integration question depends on write-to-read materialization order,
3. use [Query Control Plane](Query-Control-Plane) when the change touches snapshot, analytics-input, support, lineage, or policy-bearing contracts.
