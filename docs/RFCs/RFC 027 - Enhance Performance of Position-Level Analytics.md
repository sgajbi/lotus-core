# RFC 027 - Enhance Performance of Position-Level Analytics

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-09-01 |
| Last Updated | 2026-03-04 |
| Owners | Historical `positions-analytics` contract (superseded) |
| Depends On | RFC 017, RFC 057 |
| Scope | Historical optimization plan for retired `positions-analytics` endpoint |

## Executive Summary

RFC 027 targeted performance improvements for `POST /portfolios/{portfolio_id}/positions-analytics`.
That endpoint and surface were retired under RFC 057 and consolidated into canonical positions APIs.

As a result, RFC 027 is archived and classified `No longer relevant to this repository` as an active implementation plan.

## Original Requested Requirements (Preserved)

Original RFC 027 requested:
1. Add service-level caching for repeated positions-analytics requests.
2. Add strategic pre-calculation/persistence for common position analytics metrics.
3. Keep on-demand fallback for non-standard requests.

## Current Implementation Reality

1. `positions-analytics` endpoint is removed from lotus-core.
2. Position-level contract surface is consolidated into canonical `GET /portfolios/{portfolio_id}/positions`.
3. No separate performance-tuning plan for retired endpoint remains applicable.

Evidence:
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `tests/integration/services/query_service/test_main_app.py`
- `src/services/query_service/app/routers/positions.py`
- `docs/RFCs/RFC 017 - Position-Level Analytics API.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Cache retired positions-analytics endpoint | Not applicable (endpoint removed) | RFC 057 + OpenAPI tests |
| Pre-calc store for positions-analytics response | Not applicable in removed surface | query-service contract/state |
| Hybrid cached + on-demand behavior on positions-analytics | Superseded by canonical positions contract path | RFC 017 + RFC 057 |

## Design Reasoning and Trade-offs

1. Consolidating position-level contracts avoids duplicate API surfaces and governance drift.
2. Performance optimization should target canonical positions/query contracts, not retired endpoints.

Trade-off:
- RFC 027’s specific optimization plan is no longer directly actionable.

## Gap Assessment

No active lotus-core gap for RFC 027 as written because the target surface is retired.

## Deviations and Evolution Since Original RFC

1. RFC 057 shifted architecture from parallel analytics endpoint to canonical position contract.
2. RFC 017 now serves as the superseded design record for the removed endpoint.

## Proposed Changes

1. Keep RFC 027 archived/superseded.
2. Route any future position-query performance work through canonical positions contract governance.

## Test and Validation Evidence

1. Query-service OpenAPI test proving endpoint removal:
   - `tests/integration/services/query_service/test_main_app.py`
2. RFC 057 implementation record of endpoint retirement:
   - `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`

## Original Acceptance Criteria Alignment

Original criteria are superseded by endpoint retirement and contract consolidation.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Do we need a new RFC specifically for canonical positions endpoint performance SLOs under current architecture?

## Next Actions

1. Maintain archived status.
2. Open new RFCs only against active canonical query surfaces.
