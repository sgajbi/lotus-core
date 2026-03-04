# RFC 041 - Lookup Contract Invariant Test Gate

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` |
| Depends On | RFC 039, RFC 040 |
| Scope | Contract invariants for lookup selector endpoints |

## Executive Summary

RFC 041 introduced a dedicated test gate to keep lookup contracts stable.
It is implemented and active:
1. Contract-focused integration tests exist.
2. Tests validate shape, sorting, filtering, limit behavior, and source scoping.
3. The suite is included in existing integration test execution paths.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 041 requested:
1. Explicit integration gate for lookup contract invariants.
2. Assertions on selector contract shape and deterministic behavior.
3. CI integration for fast regression detection.

## Current Implementation Reality

Implemented:
1. `test_lookup_contract_router.py` validates lookup item shape (`id`, `label`), deterministic sort+limit, search filtering, and currency source behavior.
2. Test manifest and integration test suites include lookup contract test paths.
3. Lookup behaviors validated in this suite align with active lookup router implementations.

Evidence:
- `tests/integration/services/query_service/test_lookup_contract_router.py`
- `tests/unit/services/query_service/test_test_manifest.py`
- `src/services/query_service/app/routers/lookups.py`
- `.github/workflows/ci.yml`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Dedicated lookup invariant test gate | Implemented | `test_lookup_contract_router.py` |
| Contract shape and deterministic behavior assertions | Implemented | contract test cases |
| CI-integrated regression coverage | Implemented through existing integration test matrix/manifest | CI workflow + manifest |

## Design Reasoning and Trade-offs

1. Lightweight contract invariants catch high-impact selector regressions early.
2. Route-level deterministic behavior checks reduce UI flakiness and hidden drift.

Trade-off:
- Additional integration coverage increases test runtime modestly.

## Gap Assessment

No high-value implementation gap for RFC 041 scope.

## Deviations and Evolution Since Original RFC

1. Invariant tests now operate alongside broader reference-data router tests, giving stronger combined coverage than standalone-only gating.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.
2. Extend invariants only when lookup contract semantics expand.

## Test and Validation Evidence

1. `tests/integration/services/query_service/test_lookup_contract_router.py`
2. `tests/integration/services/query_service/test_reference_data_routers.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for baseline RFC 041 scope.

## Next Actions

1. Preserve lookup invariant tests as mandatory gate for lookup API changes.
