# Architecture

## Main runtime areas

### `query_service`

Operational read-plane API for canonical portfolio, position, transaction, market, lookup, and
reporting-oriented reads.

### `query_control_plane_service`

Governed downstream contract plane for:

- analytics inputs
- benchmark and reference inputs
- snapshots and simulations
- support and lineage
- integration policy and capabilities
- export lifecycle and supportability surfaces

### `ingestion_service`

Write-ingress and adapter upload contracts for source data.

### `event_replay_service`

Replay, ingestion-health, DLQ, and operations control-plane contracts.

### `financial_reconciliation_service`

Control execution and reconciliation run contracts.

### calculators and generators

- position calculator
- valuation calculator
- cashflow calculator
- timeseries generator

## Architecture references

- [Target Architecture](../docs/architecture/lotus-core-target-architecture.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Query Service And Control Plane Boundary](../docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)
- [RFC-0083 Target-State Gap Analysis](../docs/architecture/RFC-0083-target-state-gap-analysis.md)

## Ownership rule

If a proposed change blurs foundational source-data ownership with downstream analytics ownership,
the change belongs in architecture review before implementation.
