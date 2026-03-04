# RFC 049 - Lotus Core Snapshot Analytics De-Ownership and lotus-performance Input Contract

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-05 |
| Owners | `query-service` integration boundary governance |
| Depends On | RFC 036, RFC 063 |
| Scope | Remove analytics ownership from core-snapshot and provide raw analytics inputs for lotus-performance |

## Executive Summary

RFC 049 intent is clear and mostly realized at architectural direction level, but contract details diverged from the original text:
1. Core snapshot no longer exposes `PERFORMANCE`/`RISK_ANALYTICS` sections in current DTO contract.
2. Raw analytics input surface exists under integration analytics endpoints (`/integration/portfolios/{portfolio_id}/analytics/...`), not the exact original `performance-input` endpoint name.
3. RFC text still references governance behaviors and warning semantics not present as explicit snapshot warning fields in current contract.

Classification: `Fully implemented and aligned` after rebaselining to the delivered RFC-063 contract family.

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

Superseded details from original text:
1. Endpoint naming/schema in this RFC (`performance-input` with compact aliases like `perfDate`, `beginMv`) was superseded by implemented RFC-063 style contracts (`portfolio-timeseries`, `position-timeseries`, `reference`) with typed lineage and diagnostics.
2. Snapshot governance behavior is now covered by RFC-043 policy enforcement and metadata (`freshness`, `governance`, strict-mode section filtering/blocking), replacing earlier warning-only framing.

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
| Snapshot governance semantics when analytics sections are requested | Implemented through strict policy enforcement and governance metadata in core-snapshot | `src/services/query_service/app/routers/integration.py`; `src/services/query_service/app/dtos/core_snapshot_dto.py`; RFC-043 evidence |

## Design Reasoning and Trade-offs

1. De-ownership keeps lotus-core focused on canonical state and avoids analytics duplication with lotus-performance.
2. Rich structured analytics-input contracts improve long-term extensibility and lineage, even if they differ from early shorthand schema.

Trade-off:
- Contract/name drift between RFC text and implementation creates governance ambiguity for downstream consumers and future reviewers.

## Gap Assessment

No blocking delta remains after this contract mapping rebaseline.

## Deviations and Evolution Since Original RFC

1. Implementation evolved from a single `performance-input` endpoint concept to a broader analytics-input contract family.
2. Contract terms moved toward explicit typed metadata (`contract_version`, lineage diagnostics) rather than compact alias fields.

## Final Contract Mapping (Original -> Implemented)

| Original RFC-049 Contract Concept | Implemented Contract |
| --- | --- |
| `POST /integration/portfolios/{portfolio_id}/performance-input` | `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` |
| Position-level analytics payload embedded in same family | `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` |
| Reference metadata included ad-hoc in performance-input payload | `POST /integration/portfolios/{portfolio_id}/analytics/reference` |
| Snapshot warning semantics for analytics section requests | RFC-043 governed section filtering/strict rejection + governance provenance metadata |

## Test and Validation Evidence

1. Integration dependency tests:
   - `tests/integration/services/query_service/test_analytics_inputs_router_dependency.py`
2. Analytics input DTO and service implementation:
   - `src/services/query_service/app/dtos/analytics_input_dto.py`
   - `src/services/query_service/app/services/analytics_timeseries_service.py`

## Original Acceptance Criteria Alignment

Aligned through evolved contract family and governance supersession.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None blocking for lotus-core implementation scope.

## Next Actions

1. Keep this RFC as a bridge document pointing to RFC-063 and RFC-043 as the active contract authorities.

