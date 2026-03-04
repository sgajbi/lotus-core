# RFC 025 - Refactor Performance Engine and Enhance Monitoring

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-09-01 |
| Last Updated | 2026-03-04 |
| Owners | Historical lotus-core performance analytics surface (retired) |
| Depends On | RFC 057 (ownership and module retirement) |
| Scope | Historical proposal for in-core performance-engine refactor and query performance endpoint metrics |

## Executive Summary

RFC 025 proposed refactoring an in-core performance engine and instrumenting performance analytics endpoints in lotus-core.
This proposal no longer matches current repository boundaries:
1. Legacy in-core performance module was retired in RFC 057.
2. Legacy performance endpoints are removed from lotus-core query-service.
3. Performance analytics ownership moved out of lotus-core.

Therefore RFC 025 is archived as a historical record and is `No longer relevant to this repository`.

## Original Requested Requirements (Preserved)

Original RFC 025 requested:
1. Refactor TWR performance engine internals for maintainability/performance.
2. Preserve behavior equivalence via characterization testing.
3. Add TWR/MWR endpoint-specific monitoring in query service.

## Current Implementation Reality

1. `performance-calculator-engine` is removed from lotus-core as legacy module under RFC 057.
2. Query service no longer exposes legacy performance endpoints (`/portfolios/{portfolio_id}/performance`, `/performance/mwr`).
3. RFC text itself contains numbering drift (`RFC 026` in-body), confirming document staleness relative to current governance stream.

Evidence:
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `tests/integration/services/query_service/test_main_app.py`
- `src/services/query_service/app/main.py` and router set (no performance router)

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| In-core performance engine refactor | Not applicable (module retired) | RFC 057 legacy retirement section |
| Query performance endpoint metrics | Not applicable to removed endpoint surface | query-service OpenAPI contract tests |
| Characterization-driven refactor in lotus-core | Not applicable in current ownership model | RFC 057 ownership boundaries |

## Design Reasoning and Trade-offs

1. Keeping performance analytics out of lotus-core reduces contract overlap and ownership drift.
2. Lotus-core remains focused on canonical data/state contracts and simulation/integration capabilities.

Trade-off:
- Historical in-core optimization proposals are no longer actionable here and must be re-homed to the owning performance repository if still needed.

## Gap Assessment

No lotus-core implementation gap is tracked for RFC 025 because scope is out-of-repo.

## Deviations and Evolution Since Original RFC

1. RFC 057 superseded the premise by retiring legacy performance assets from lotus-core.
2. Downstream analytics ownership separation made this RFC non-actionable in this repository.

## Proposed Changes

1. Keep RFC 025 archived in lotus-core.
2. If requirements remain valuable, re-open as a new RFC in the owning performance app repository with current architecture context.

## Test and Validation Evidence

1. OpenAPI tests confirm performance endpoints are absent:
   - `tests/integration/services/query_service/test_main_app.py`
2. RFC 057 implementation record confirms module retirement:
   - `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`

## Original Acceptance Criteria Alignment

Original criteria are superseded by ownership and module retirement decisions.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Which target repository will own any future TWR/MWR engine refactor RFC derived from this historical proposal?

## Next Actions

1. Keep as archived/superseded in lotus-core.
2. Reference lotus-performance (or current owning app) for any active implementation planning.
