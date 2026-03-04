# RFC 017 - Position-Level Analytics API

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-31 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core query-service (canonical positions), superseded endpoint design |
| Depends On | RFC 057 |
| Scope | Archived endpoint design; superseded by canonical `GET /portfolios/{portfolio_id}/positions` |

## Executive Summary

RFC 017 originally proposed a dedicated `POST /portfolios/{portfolio_id}/positions-analytics` endpoint.
This design was superseded by RFC 057:
1. `positions-analytics` endpoint removed from lotus-core.
2. Canonical position-level fields consolidated into `GET /portfolios/{portfolio_id}/positions`.

## Original Requested Requirements (Preserved)

Original RFC 017 requested:
1. Configurable position-analytics endpoint with sectioned response.
2. Per-position enrichment: valuation, instrument details, income, performance, weights, held-since.
3. Epoch-consistent calculations.
4. Reuse of existing performance engine for position-level return logic.

## Current Implementation Reality

1. `POST /portfolios/{portfolio_id}/positions-analytics` is removed from lotus-core.
2. Canonical `GET /portfolios/{portfolio_id}/positions` now serves consolidated position-level fields.
3. Endpoint consolidation and legacy removal were implemented under RFC 057.

Evidence:
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `src/services/query_service/app/routers/positions.py`
- `src/services/query_service/app/services/position_service.py`
- `src/services/query_service/app/dtos/position_dto.py`
- `docs/RFCs/RFC 027 - Enhance Performance of Position-Level Analytics.md` (supersession note)

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Dedicated positions-analytics endpoint | Removed/superseded | RFC 057 execution notes |
| Position-level enriched data | Consolidated into canonical `positions` endpoint | positions router/service/dto |
| Epoch-consistent position retrieval | Maintained through canonical query paths | position repository/service behavior |
| Separate performance-heavy position analytics surface | Not retained as separate contract | endpoint retirement under RFC 057 |

## Design Reasoning and Trade-offs

1. **Why remove separate endpoint**: avoids contract duplication and drift between `positions` and `positions-analytics`.
2. **Why consolidate into canonical positions**: cleaner API-first surface with clearer ownership and lower maintenance.
3. **Trade-off**: less flexible sectioned analytics payload in exchange for simpler, more stable contract governance.

## Gap Assessment

No implementation gap remains for RFC 017 as originally proposed endpoint design because it is intentionally superseded.

## Deviations and Evolution Since Original RFC

1. Endpoint strategy shifted from additive analytics API to contract consolidation.
2. Core position contract now carries the authoritative position-level surface.

## Proposed Changes

1. Keep RFC 017 archived as superseded design record.
2. Continue position-level contract evolution through canonical `positions` API RFC stream.

## Test and Validation Evidence

1. Canonical positions endpoint contract and integration tests:
   - query-service positions router/service tests and DTO contract tests
2. RFC 057 implementation record documenting endpoint removal and consolidation.

## Original Acceptance Criteria Alignment

Original endpoint-specific acceptance criteria are superseded.
Current acceptance is fulfilled through canonical positions contract consolidation and removal of parallel analytics surface.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should any remaining analytics-only fields be explicitly migrated into canonical positions contract docs to avoid future parallel endpoint proposals?

## Next Actions

1. Keep RFC 017 as archived/superseded.
2. Route all position-level contract enhancements through canonical `positions` API governance.
