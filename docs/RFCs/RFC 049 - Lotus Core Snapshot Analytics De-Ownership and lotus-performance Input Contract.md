# RFC 049 - Lotus Core Snapshot Analytics De-Ownership and lotus-performance Input Contract

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` integration boundary governance |
| Depends On | RFC 036, RFC 063 |
| Scope | Remove analytics ownership from core-snapshot and provide raw analytics inputs for lotus-performance |

## Executive Summary

RFC 049 intent is clear and mostly realized at architectural direction level, but contract details diverged from the original text:
1. Core snapshot no longer exposes `PERFORMANCE`/`RISK_ANALYTICS` sections in current DTO contract.
2. Raw analytics input surface exists under integration analytics endpoints (`/integration/portfolios/{portfolio_id}/analytics/...`), not the exact original `performance-input` endpoint name.
3. RFC text still references governance behaviors and warning semantics not present as explicit snapshot warning fields in current contract.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 049 requested:
1. Explicit de-ownership of analytics sections from `core-snapshot`.
2. New raw performance input endpoint contract for lotus-performance.
3. Governance behavior when analytics sections are requested from snapshot (filter/warn or strict reject).

## Current Implementation Reality

Implemented:
1. `core-snapshot` section enum includes baseline/simulation/portfolio totals/enrichment only; no `PERFORMANCE` or `RISK_ANALYTICS` sections.
2. Integration analytics-input contracts exist and provide raw timeseries/reference data for downstream analytics:
   - `/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
   - `/integration/portfolios/{portfolio_id}/analytics/position-timeseries`
   - `/integration/portfolios/{portfolio_id}/analytics/reference`
3. DTOs and service implementations for these analytics input contracts are present and test-covered.

Not fully aligned to original text:
1. Endpoint naming/schema in RFC (`performance-input` with field aliases like `perfDate`, `beginMv`) differs from implemented RFC-063 style contract (`rfc_063_v1` structured DTOs).
2. Explicit snapshot warning code semantics described here are not represented in current core-snapshot response model.

Evidence:
- `src/services/query_service/app/dtos/core_snapshot_dto.py`
- `src/services/query_service/app/routers/analytics_inputs.py`
- `src/services/query_service/app/dtos/analytics_input_dto.py`
- `src/services/query_service/app/services/analytics_timeseries_service.py`
- `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Remove analytics sections from core-snapshot | Implemented | `CoreSnapshotSection` enum |
| Provide raw analytics input contract | Implemented with evolved endpoint family and schema | analytics inputs router/DTO/service |
| Snapshot filter/warn governance semantics | Partially implemented / not explicit in snapshot response | snapshot DTO/service behavior |

## Design Reasoning and Trade-offs

1. De-ownership keeps lotus-core focused on canonical state and avoids analytics duplication with lotus-performance.
2. Rich structured analytics-input contracts improve long-term extensibility and lineage, even if they differ from early shorthand schema.

Trade-off:
- Contract/name drift between RFC text and implementation creates governance ambiguity for downstream consumers and future reviewers.

## Gap Assessment

Remaining delta:
1. Rebaseline RFC 049 to current implemented RFC-063-style analytics input contract and explicitly document superseded endpoint naming/schema.
2. Decide whether snapshot warning semantics are required and, if not, remove from RFC to avoid false expectations.

## Deviations and Evolution Since Original RFC

1. Implementation evolved from a single `performance-input` endpoint concept to a broader analytics-input contract family.
2. Contract terms moved toward explicit typed metadata (`contract_version`, lineage diagnostics) rather than compact alias fields.

## Proposed Changes

1. Keep classification as `Partially implemented`.
2. Publish a consolidated “final contract mapping” section in this RFC linking original proposal to implemented endpoints.

## Test and Validation Evidence

1. Integration dependency tests:
   - `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`
2. Analytics input DTO and service implementation:
   - `src/services/query_service/app/dtos/analytics_input_dto.py`
   - `src/services/query_service/app/services/analytics_timeseries_service.py`

## Original Acceptance Criteria Alignment

Partially aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should RFC 049 be merged/superseded by RFC 063 documentation to eliminate duplicate contract narratives?

## Next Actions

1. Reconcile RFC 049 with current analytics-input endpoint naming and schema.
2. Explicitly document snapshot warning behavior as implemented or removed.

