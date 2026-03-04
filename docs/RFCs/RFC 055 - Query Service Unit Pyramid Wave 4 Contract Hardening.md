# RFC 055 - Query Service Unit Pyramid Wave 4 Contract Hardening

| Metadata | Value |
| --- | --- |
| Status | Deprecated |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | query-service quality gates (historical) |
| Depends On | RFC 054, pre-RFC-056 query scope |
| Scope | Unit-heavy DTO contract testing wave |

## Executive Summary

RFC 055 targeted unit-heavy contract validation for DTOs that included legacy in-core domains.
That scope is no longer aligned with current lotus-core ownership:
1. Referenced review/performance/MWR contract families are not active query-service domains in current architecture.
2. Query-service DTO contract testing exists but has evolved around current domains (`analytics_inputs`, `simulation`, `integration`, `lookup`), not this RFC's listed legacy surfaces.

Classification: `Outdated (requires revision)`.

## Original Requested Requirements (Preserved)

Original RFC 055 requested:
1. Increase unit-test pyramid depth with DTO-heavy contract tests.
2. Cover DTO contracts including:
   - performance contracts,
   - MWR requests,
   - review alias/section contracts,
   - position analytics aliases/enums.

## Current Implementation Reality

Implemented in spirit:
1. DTO-focused unit tests exist for active query-service contracts (for example analytics input, core snapshot, lookup).

Not aligned to original listed scope:
1. Legacy review/performance contract families referenced by RFC are no longer owned by active lotus-core query-service surface.
2. No dedicated wave-4 module matching the original exact target set exists because ownership and API set changed.

Evidence:
- `tests/unit/services/query_service/dtos/test_analytics_input_dto.py`
- `tests/unit/services/query_service/dtos/test_core_snapshot_dto.py`
- `tests/unit/services/query_service/dtos/test_lookup_dto.py`
- `src/services/query_service/app/dtos` current inventory
- RFC 056/057 de-ownership context already reflected in repository

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Unit-heavy DTO contract hardening | Partially present for active domains | DTO unit test modules |
| Performance/MWR/review DTO wave | Not applicable to current query-service ownership | current DTO inventory + de-ownership context |
| Position analytics alias/enum contracts (legacy framing) | Evolved into analytics-input contract tests with different schema | analytics-input DTO tests |

## Design Reasoning and Trade-offs

1. Unit pyramid hardening remains valid as a principle.
2. Keeping legacy-domain-specific targets in active RFC text creates misalignment with current architecture and ownership.

Trade-off:
- Without rebaselining, teams may spend effort chasing obsolete targets rather than current contract risk hotspots.

## Gap Assessment

Remaining delta:
1. Replace RFC 055 scope with a current-era DTO pyramid hardening RFC bound to active query-service domains and ownership boundaries.

## Deviations and Evolution Since Original RFC

1. Post-RFC-056/057 ownership changes shifted contract surfaces materially.
2. DTO testing focus moved toward active integration/simulation/analytics contracts.

## Proposed Changes

1. Mark RFC 055 as deprecated historical record.
2. Create successor RFC for current DTO pyramid strategy tied to active domains.

## Test and Validation Evidence

1. `tests/unit/services/query_service/dtos/test_analytics_input_dto.py`
2. `tests/unit/services/query_service/dtos/test_core_snapshot_dto.py`
3. `tests/unit/services/query_service/dtos/test_lookup_dto.py`

## Original Acceptance Criteria Alignment

Partially aligned in principle, not aligned in listed domain targets.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should successor pyramid RFC be lotus-core-only or platform-wide for all query-like services?

## Next Actions

1. Draft successor DTO pyramid RFC mapped to active query-service contract families.
