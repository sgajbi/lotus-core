# RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints

| Field | Value |
| --- | --- |
| Status | Deprecated |
| Created | 2026-02-27 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | RFC 035, RFC 057 |
| Related Standards | `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`; lotus-platform API ownership standards |
| Scope | In repo |

## Executive Summary
RFC 056 requested runtime hard-disable (`410 Gone`) for legacy query endpoints that belonged to `lotus-performance`, `lotus-risk`, and `lotus-report`.

Current system evolution (RFC 057 wave) went further: those endpoints are removed from active query-service contract surfaces. This enforces service boundaries, but the RFC text now reflects a transitional mechanism that is no longer consistently represented in active contracts/tests.

## Original Requested Requirements (Preserved)
1. Hard-disable legacy query endpoints with explicit migration guidance.
2. Return deterministic `410 Gone` responses (instead of executing local analytics/reporting logic).
3. Keep temporary route surfaces for explicit migration messaging.
4. Update tests/docs/runbooks to align with migrated ownership.

Endpoints listed in the original request:
1. `POST /portfolios/{portfolio_id}/performance`
2. `POST /portfolios/{portfolio_id}/performance/mwr`
3. `POST /portfolios/{portfolio_id}/risk`
4. `POST /portfolios/{portfolio_id}/concentration`
5. `POST /portfolios/{portfolio_id}/summary`
6. `POST /portfolios/{portfolio_id}/review`

## Current Implementation Reality
1. Query-service OpenAPI no longer exposes these legacy paths.
2. Query-service codebase has no active routers for these endpoint families.
3. Contract test asserts these paths are absent from OpenAPI.
4. E2E tests now consistently use shared legacy-endpoint assertions that accept the approved boundary policy (`404` or `410`) while preserving migration-hint checks when present.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Disable legacy runtime logic | Implemented | `src/services/query_service/app/routers` (no legacy analytics/reporting routers); `tests/integration/services/query_service/test_main_app.py` |
| Return migration guidance and enforce disabled behavior on legacy paths | Implemented with normalized compatibility policy (`404` or `410`) | `tests/e2e/assertions.py`; `tests/e2e/test_performance_pipeline.py`; `tests/e2e/test_summary_pipeline.py`; `tests/e2e/test_review_pipeline.py`; `tests/e2e/test_concentration_pipeline.py`; `tests/e2e/test_complex_portfolio_lifecycle.py` |
| Remove deprecated surfaces from active API contract | Implemented | `tests/integration/services/query_service/test_main_app.py` (`test_openapi_hides_migrated_legacy_endpoints`) |
| Align docs with service ownership boundaries | Implemented at architecture level; RFC text now stale as transitional-only | `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md` |

## Design Reasoning and Trade-offs
1. Removing endpoints from active contract surface reduces accidental reuse and ownership ambiguity.
2. `410` transitional routes improve migration ergonomics, but keeping them indefinitely increases maintenance and contract clutter.
3. Current state prioritizes hard boundary enforcement over migration UX continuity.

## Gap Assessment
1. No blocking implementation gap remains for RFC-056 behavior normalization; legacy path policy is now codified in shared E2E assertions.

## Deviations and Evolution Since Original RFC
1. Original RFC centered on retained routes returning `410`.
2. Implemented system moved to route removal from OpenAPI/active contract.
3. Operationally this is stricter than original ask, but the RFC should be revised to document final policy.

## Proposed Changes
1. Keep RFC 056 as a historical transition RFC (deprecated).
2. Retain explicit compatibility policy (`404` or `410`) in shared assertion helpers to avoid brittle environment-specific failures.

## Test and Validation Evidence
1. `tests/integration/services/query_service/test_main_app.py`
2. `tests/e2e/test_performance_pipeline.py`
3. `tests/e2e/test_summary_pipeline.py`
4. `tests/e2e/test_review_pipeline.py`
5. `tests/e2e/test_concentration_pipeline.py`
6. `tests/e2e/test_complex_portfolio_lifecycle.py`

## Original Acceptance Criteria Alignment
1. Legacy endpoints no longer execute lotus-core analytics/reporting logic: aligned.
2. Deterministic disabled behavior plus migration guidance compatibility policy: aligned.
3. Boundary ownership enforcement: aligned.

## Rollout and Backward Compatibility
1. Backward compatibility for legacy endpoint callers is intentionally reduced.
2. Migration should be handled through service-level routing/orchestration in owning apps (`lotus-performance`, `lotus-risk`, `lotus-report`) and gateway policy.

## Open Questions
1. Should lotus-core keep minimal `410` compatibility shims for one release window, or enforce pure removal (`404`) as the long-term contract?
2. Where should migration messaging be canonicalized if paths are removed (gateway, platform docs, or both)?

## Next Actions
1. Keep RFC 056 as deprecated transitional history; point active boundary design to RFC 057.
