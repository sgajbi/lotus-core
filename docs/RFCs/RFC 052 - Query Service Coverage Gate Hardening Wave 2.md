# RFC 052 - Query Service Coverage Gate Hardening Wave 2

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | query-service quality gates |
| Depends On | RFC 050, coverage gate workflow |
| Scope | Expand branch coverage and integration-lite suite breadth for policy/control-plane behaviors |

## Executive Summary

RFC 052 is implemented.
Wave-2 hardening outcomes are present:
1. Integration policy and capabilities override edge-case tests exist.
2. Query-service lifespan logging test exists.
3. Capabilities router dependency coverage is included through integration-lite suite discovery.
4. Coverage gate framework now enforces high threshold in follow-up RFC (053).

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 052 requested:
1. Add branch-focused policy/capabilities tests.
2. Add app lifecycle/lifespan coverage.
3. Ensure these tests are included in enforced coverage gate suites.

## Current Implementation Reality

Implemented:
1. `test_integration_service.py` includes tenant/default/strict/allowed-section branch tests.
2. `test_capabilities_service.py` includes malformed JSON/non-object/override edge cases.
3. `test_main_app.py` includes lifespan startup/shutdown log assertions.
4. Integration-lite suite discovery in `scripts/test_manifest.py` includes query router dependency tests, which includes capabilities router tests.

Evidence:
- `tests/unit/services/query_service/services/test_integration_service.py`
- `tests/unit/services/query_service/services/test_capabilities_service.py`
- `tests/integration/services/query_service/test_capabilities_router_dependency.py`
- `tests/integration/services/query_service/test_main_app.py`
- `scripts/test_manifest.py`
- `scripts/coverage_gate.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Policy branch test hardening | Implemented | integration service unit tests |
| Capabilities normalization/override hardening | Implemented | capabilities service unit tests |
| Lifespan logging test | Implemented | `test_main_app.py` lifespan test |
| Coverage gate inclusion of capabilities router test | Implemented through integration-lite router test discovery | `test_manifest.py` + capabilities integration test |

## Design Reasoning and Trade-offs

1. Hardening control-plane branches reduces regression risk in tenant-policy-driven contracts.
2. Router-dependency integration tests provide low-cost API-contract confidence.

Trade-off:
- Incremental CI runtime increase due to added tests.

## Gap Assessment

No high-value implementation gap identified for RFC 052 scope.

## Deviations and Evolution Since Original RFC

1. Capabilities inclusion is achieved via generic router discovery in `test_manifest.py` rather than a single hardcoded list entry in `coverage_gate.py`.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. `tests/unit/services/query_service/services/test_integration_service.py`
2. `tests/unit/services/query_service/services/test_capabilities_service.py`
3. `tests/integration/services/query_service/test_main_app.py`
4. `tests/integration/services/query_service/test_capabilities_router_dependency.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for wave-2 scope.

## Next Actions

1. Keep branch-focused policy test sets updated as integration contract policy model evolves.
