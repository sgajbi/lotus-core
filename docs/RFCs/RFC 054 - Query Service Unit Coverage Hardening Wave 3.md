# RFC 054 - Query Service Unit Coverage Hardening Wave 3

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | query-service quality gates |
| Depends On | RFC 053 |
| Scope | Targeted unit-test branch hardening for query-service |

## Executive Summary

RFC 054 aimed to harden selected unit-coverage branches.
Current reality is mixed:
1. Simulation and integration branch tests requested by this RFC are implemented.
2. `lookup_dto` contract unit tests are implemented.
3. Referenced `performance_service` scope is stale because that service is no longer part of current query-service module set.

Classification: `Partially implemented (requires enhancement)`.

## Original Requested Requirements (Preserved)

Original RFC 054 requested:
1. Add unit tests for selected edge paths in:
   - `performance_service`,
   - `simulation_service`,
   - `integration_service`.
2. Add direct tests for `lookup_dto` model contracts.

## Current Implementation Reality

Implemented:
1. `simulation_service` has strong unit coverage including happy and guard paths.
2. `integration_service` includes branch tests for include-section omission and policy resolution variants.
3. `lookup_dto` contract tests exist.

Outdated/partial:
1. `performance_service` no longer exists in current query-service (`src/services/query_service/app/services`), so that part of RFC cannot be implemented as written.

Evidence:
- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/unit/services/query_service/services/test_integration_service.py`
- `tests/unit/services/query_service/dtos/test_lookup_dto.py`
- `src/services/query_service/app/services` directory inventory

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Simulation service branch tests | Implemented | simulation service unit tests |
| Integration service omitted-include_sections branch tests | Implemented | integration service unit tests |
| Lookup DTO tests | Implemented | lookup DTO unit tests |
| Performance service branch tests | Not applicable to current codebase (service removed/de-owned) | service directory inventory |

## Design Reasoning and Trade-offs

1. High-signal branch testing remains useful and is partially delivered.
2. Legacy module references in RFC text create governance drift and confusion.

Trade-off:
- Maintaining stale RFC scope can produce false backlog noise and mis-prioritized effort.

## Gap Assessment

Remaining delta:
1. Rebaseline RFC 054 scope to active query-service modules only (for example analytics-inputs, operations, integration, simulation).

## Deviations and Evolution Since Original RFC

1. Query-service responsibility shifted after legacy endpoint/service de-ownership, making some original test targets obsolete.

## Proposed Changes

1. Keep classification as `Partially implemented`.
2. Update RFC text to current module ownership and remove legacy `performance_service` dependency.

## Test and Validation Evidence

1. `tests/unit/services/query_service/services/test_simulation_service.py`
2. `tests/unit/services/query_service/services/test_integration_service.py`
3. `tests/unit/services/query_service/dtos/test_lookup_dto.py`

## Original Acceptance Criteria Alignment

Partially aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Which active query-service modules should replace legacy performance-service targets for wave-3 equivalence?

## Next Actions

1. Rebaseline wave-3 test objectives against current module map and coverage hotspots.
