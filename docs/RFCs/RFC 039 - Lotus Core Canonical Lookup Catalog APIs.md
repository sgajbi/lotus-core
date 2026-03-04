# RFC 039 - Lotus Core Canonical Lookup Catalog APIs

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` lookup contracts |
| Depends On | RFC 039 baseline, RFC 040 optimization/filter controls, RFC 041 invariant test gate |
| Scope | Canonical selector catalogs for portfolios, instruments, currencies |

## Executive Summary

RFC 039 established lotus-core-owned lookup catalogs for UI/gateway selector use cases.
The baseline decision is implemented and operating:
1. Canonical lookup endpoints exist for portfolios, instruments, and currencies.
2. Shared response contract uses stable `items[{id,label}]` shape.
3. Lookup ownership is centralized in query-service.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 039 requested:
1. Canonical lookup endpoints for portfolio, instrument, and currency selectors.
2. Uniform contract shape for selector catalogs.
3. Backend-owned mapping logic so downstream apps do not duplicate derivation logic.

## Current Implementation Reality

Implemented:
1. Endpoints exist under `/lookups/portfolios`, `/lookups/instruments`, and `/lookups/currencies`.
2. Uniform `LookupResponse` contract with `items` list is returned.
3. Portfolio and instrument lookups map canonical identifiers to user-facing selector labels.
4. Currency lookup derives distinct uppercase codes from both portfolio base currencies and instrument reference data.
5. Lookup routes are documented in OpenAPI and validated in integration tests.

Evidence:
- `src/services/query_service/app/routers/lookups.py`
- `src/services/query_service/app/dtos/lookup_dto.py`
- `tests/integration/services/query_service/test_reference_data_routers.py`
- `tests/integration/services/query_service/test_lookup_contract_router.py`
- `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Portfolio lookup catalog | Implemented | lookups router + integration tests |
| Instrument lookup catalog | Implemented | lookups router + integration tests |
| Currency lookup catalog | Implemented | lookups router currency derivation logic + tests |
| Uniform selector contract shape | Implemented (`id`, `label`) | lookup DTO + contract tests |
| Backend-owned derivation logic | Implemented in query-service | lookups router/service calls |

## Design Reasoning and Trade-offs

1. Consolidating lookup catalogs in lotus-core removes repeated mapping logic in consumers.
2. Contract uniformity reduces UI/gateway complexity and regression risk.
3. Distinct uppercase currency derivation provides deterministic selector normalization.

Trade-off:
- Currency catalog currently reflects observed data sources, not a dedicated enterprise currency master.

## Gap Assessment

No high-value implementation gap for RFC 039 baseline.
Future currency-master introduction remains an enhancement opportunity, not a correctness defect.

## Deviations and Evolution Since Original RFC

1. RFC 040 and RFC 041 subsequently added filtering/performance controls and invariant contract tests, strengthening the original baseline.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Treat future currency-master integration as optional follow-on scope.

## Test and Validation Evidence

1. Reference-data lookup integration tests:
   - `tests/integration/services/query_service/test_reference_data_routers.py`
2. Lookup invariant contract suite:
   - `tests/integration/services/query_service/test_lookup_contract_router.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Canonical endpoints and response shape are implemented.
2. Selector derivation logic is centralized in lotus-core.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should future entitlement-aware scoping live in these endpoints directly or in a policy-aware lookup adapter layer?

## Next Actions

1. Keep lookup contract invariants green as catalog metadata evolves.
