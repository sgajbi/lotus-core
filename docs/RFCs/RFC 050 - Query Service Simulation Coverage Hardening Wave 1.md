# RFC 050 - Query Service Simulation Coverage Hardening Wave 1

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | `query-service` test quality |
| Depends On | RFC 046A |
| Scope | First-wave simulation-focused test hardening for query-service |

## Executive Summary

RFC 050 delivered targeted simulation test hardening and is implemented:
1. Repository unit tests cover key simulation persistence edge behavior.
2. Service unit tests cover lifecycle/guard/projection branches.
3. Router integration tests cover service-error to HTTP mapping for simulation endpoints.
4. Test dependency completeness concern (`openpyxl`) is resolved in test requirements.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 050 requested:
1. Harden simulation module coverage via focused repository/service/router test additions.
2. Reduce regression risk around guardrails and error mapping.
3. Ensure test collection dependencies are complete.

## Current Implementation Reality

Implemented:
1. Simulation repository tests cover create/get/close/add/delete and rollback behavior.
2. Simulation service tests cover session validation, change semantics, and projection paths.
3. Simulation router dependency tests verify request/response mappings and expected error status behavior.
4. `openpyxl` is present in `tests/requirements.txt`.

Evidence:
- `tests/unit/services/query_service/repositories/test_simulation_repository.py`
- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/integration/services/query_service/test_simulation_router_dependency.py`
- `tests/requirements.txt`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Repository simulation branch tests | Implemented | simulation repository test suite |
| Service guard/projection tests | Implemented | simulation service test suite |
| Router error/status mapping tests | Implemented | simulation router dependency tests |
| Dependency completeness for collection | Implemented | `tests/requirements.txt` includes `openpyxl` |

## Design Reasoning and Trade-offs

1. Focused branch coverage in high-risk simulation modules provides disproportionate quality gains.
2. Explicit router mapping tests prevent silent HTTP contract drift.

Trade-off:
- Additional targeted tests slightly increase runtime but materially reduce regression risk.

## Gap Assessment

No high-value implementation gap identified for RFC 050 wave-1 scope.

## Deviations and Evolution Since Original RFC

1. Broader query-service coverage hardening continued in later RFCs (051-055), making this RFC a completed first wave in a larger sequence.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. `tests/unit/services/query_service/repositories/test_simulation_repository.py`
2. `tests/unit/services/query_service/services/test_simulation_service.py`
3. `tests/integration/services/query_service/test_simulation_router_dependency.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for wave-1 scope; subsequent coverage hardening is tracked in later RFCs.

## Next Actions

1. Maintain simulation test depth as session/snapshot contracts evolve.
