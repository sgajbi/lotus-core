# RFC 036 - lotus-core Core Snapshot Contract for lotus-performance and lotus-manage

- Date: 2026-02-23
- Services Affected: `query-service`, `lotus-performance`, `lotus-advise`, lotus-gateway
- Status: Implemented (v1)

## Summary

Introduces a versioned lotus-core integration contract endpoint that provides a canonical as-of snapshot for lotus-performance/lotus-manage consumption.

## Endpoint

- `POST /integration/portfolios/{portfolio_id}/core-snapshot`

## Contract Properties

1. `contractVersion` for schema versioning.
2. `as_of_date` control in request payload.
3. `include_sections` to choose payload breadth per consumer use case.
4. `consumer_system` field for integration traceability.

## Response Composition

1. Canonical lotus-core portfolio record.
2. As-of snapshot assembled by lotus-core review orchestration.

## Why This Matters

1. Gives lotus-performance and lotus-manage a stable lotus-core-owned boundary.
2. Reduces duplicate data-access logic in downstream systems.
3. Enables controlled evolution via explicit versioning.

## Next Steps

1. Completed via `RFC 043 - lotus-core Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance)`:
   - explicit provenance/freshness metadata,
   - policy-driven section governance controls.
2. Continue lotus-gateway-level adapters to map lotus-core contract into UI-specific view models.

