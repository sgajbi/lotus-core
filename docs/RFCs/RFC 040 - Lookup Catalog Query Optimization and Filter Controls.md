# RFC 040 - Lookup Catalog Query Optimization and Filter Controls

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` lookup contracts |
| Depends On | RFC 039 lookup baseline, RFC 041 lookup invariant gate |
| Scope | Filtering, ordering, and payload controls for lookup catalogs |

## Executive Summary

RFC 040 extends RFC 039 with server-side query controls and deterministic behavior.
It is implemented in current query-service:
1. Portfolio lookup supports scoped filtering and query/limit controls.
2. Instrument lookup supports product-type and text filtering.
3. Currency lookup supports source-scoped derivation plus query/limit controls.
4. Deterministic sort and limit behavior is validated in integration tests.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 040 requested:
1. Add lookup filter/query parameters to reduce payload volume and improve selector UX.
2. Ensure deterministic ordering for stable UI behavior.
3. Enforce server-side limits for oversized catalogs.

## Current Implementation Reality

Implemented:
1. `/lookups/portfolios` supports `client_id`, `booking_center_code`, `q`, and `limit`.
2. `/lookups/instruments` supports `product_type`, `q`, and `limit`.
3. `/lookups/currencies` supports `source` (`ALL|PORTFOLIOS|INSTRUMENTS`), `q`, `limit`, and `instrument_page_limit`.
4. Shared filter helper enforces:
   - case-insensitive matching on `id` and `label`,
   - deterministic sorting by `id`,
   - server-side result limiting.
5. Integration suites verify filters, sort order, and source scoping behavior.

Evidence:
- `src/services/query_service/app/routers/lookups.py`
- `tests/integration/services/query_service/test_reference_data_routers.py`
- `tests/integration/services/query_service/test_lookup_contract_router.py`
- `docs/RFCs/RFC 041 - Lookup Contract Invariant Test Gate.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Portfolio lookup filter controls | Implemented | lookups router + integration tests |
| Instrument lookup filter controls | Implemented | lookups router + integration tests |
| Currency source/query/limit controls | Implemented | lookups router + integration tests |
| Deterministic sorting | Implemented (sorted by `id`) | `_filter_limit_sort_items` helper |
| Server-side limit enforcement | Implemented | query params + helper + tests |

## Design Reasoning and Trade-offs

1. Server-side filtering reduces client-side load and network overhead.
2. Deterministic ordering prevents subtle UI drift and flaky selector behavior.
3. Source-scoped currency lookup allows targeted selector use cases without separate endpoint families.

Trade-off:
- Parameter matrix expansion increases validation/test surface area and requires invariant contract coverage.

## Gap Assessment

No high-value implementation gap for RFC 040 baseline scope.

## Deviations and Evolution Since Original RFC

1. Naming in implementation uses current canonical filter fields (`client_id`, `booking_center_code`) rather than earlier shorthand.
2. Invariant test gate (RFC 041) formalized ongoing regression protection.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Continue extending lookup controls only when backed by measured selector-scale needs.

## Test and Validation Evidence

1. Query-service reference data router tests:
   - `tests/integration/services/query_service/test_reference_data_routers.py`
2. Lookup invariant contract tests:
   - `tests/integration/services/query_service/test_lookup_contract_router.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Filter controls, deterministic sorting, and limit enforcement are implemented and tested.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. At what catalog scale should lookup endpoints adopt cursor/token pagination rather than bounded list responses?

## Next Actions

1. Keep RFC 041 invariant suite as mandatory gate for any lookup API changes.
