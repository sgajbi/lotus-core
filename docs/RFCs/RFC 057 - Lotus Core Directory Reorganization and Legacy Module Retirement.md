# RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-27 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core maintainers |
| Depends On | RFC 035, RFC 036, RFC 046A, RFC 049, RFC 056 |
| Related Standards | lotus-platform API ownership and API-first standards |
| Scope | Cross-repo |

## Executive Summary
RFC 057 executed the structural boundary reset for `lotus-core`: legacy analytics/reporting ownership was removed, core data and simulation contracts were retained, and ingestion/query boundaries were hardened for API-first integration.

The implementation is substantially complete and aligned with the target role of lotus-core as canonical state/calculation backbone, not downstream analytics/reporting owner.

## Original Requested Requirements (Preserved)
1. Reorganize boundaries to reflect current ownership.
2. Remove legacy analytics modules and stale docs from active core scope.
3. Enforce API-first integration contracts and reduce DB-bypass guidance.
4. Consolidate duplicate position contract surfaces (`positions-analytics` into canonical `positions`).
5. Keep simulation workflows as first-class capabilities.
6. Clarify canonical upstream ingestion model and adapter modes.
7. Deliver changes incrementally with low-risk PR slices and test gates.

## Current Implementation Reality
1. Legacy analytics libraries and corresponding feature docs are removed from active tree.
2. Legacy query endpoints are absent from active query-service OpenAPI contract.
3. `positions-analytics` endpoint is removed; canonical positions surface remains.
4. Adapter-mode ingestion endpoints (`portfolio-bundle`, upload APIs) are feature-flag gated and return explicit `410` when disabled.
5. Integration capability/policy endpoints are active for consumer awareness and governance.
6. Simulation and integration contract surfaces remain available.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Remove legacy analytics modules/docs | Implemented | Missing paths: `src/libs/risk-analytics-engine`, `src/libs/performance-calculator-engine`, `src/libs/concentration-analytics-engine`, `docs/features/risk_analytics`, `docs/features/performance_analytics`, `docs/features/concentration_analytics`, `docs/features/portfolio_review`, `docs/features/portfolio_summary` |
| Remove `positions-analytics` parallel surface | Implemented | `tests/integration/services/query_service/test_main_app.py` asserts `/portfolios/{portfolio_id}/positions-analytics` absent |
| Harden adapter-mode ingestion boundaries | Implemented | `src/services/ingestion_service/app/adapter_mode.py`; `src/services/ingestion_service/app/routers/portfolio_bundle.py`; `src/services/ingestion_service/app/routers/uploads.py` |
| Keep simulation contracts first class | Implemented | `src/services/query_control_plane_service/app/routers/simulation.py`; `tests/integration/services/query_service/test_simulation_router_dependency.py` |
| Keep integration policy/capability contracts | Implemented | `src/services/query_control_plane_service/app/routers/capabilities.py`; `src/services/query_control_plane_service/app/routers/integration.py`; capabilities tests |

## Design Reasoning and Trade-offs
1. Strict ownership separation reduces drift and duplicate business logic.
2. Removing legacy surfaces can break stale consumers but lowers long-term ambiguity.
3. Feature-flagged adapter paths preserve controlled onboarding while keeping canonical enterprise ingestion model explicit.
4. Consolidating position contracts reduces duplicate semantics and query drift.

## Gap Assessment
1. Some historical tests/docs still carry transitional assumptions for removed legacy paths.
2. Cross-repo migration governance remains distributed and requires continued platform coordination.

## Deviations and Evolution Since Original RFC
1. The RFC envisioned broad directory layering changes; current implementation focused first on high-impact ownership and contract boundaries.
2. Most runtime-critical outcomes are complete; remaining work is primarily governance/documentation hygiene rather than core behavior gaps.

## Proposed Changes
1. Keep RFC 057 as implemented baseline architecture decision.
2. Route remaining follow-ups to successor governance RFCs/deltas (cross-repo boundary and vocabulary governance).

## Test and Validation Evidence
1. `tests/integration/services/query_service/test_main_app.py`
2. `tests/integration/services/query_service/test_capabilities_router_dependency.py`
3. `tests/integration/services/query_service/test_simulation_router_dependency.py`
4. `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
5. `src/services/ingestion_service/app/adapter_mode.py`

## Original Acceptance Criteria Alignment
1. Legacy analytics modules removed: aligned.
2. Clear core ownership boundaries: aligned.
3. API-first integration model preserved: aligned.
4. Position contract consolidation: aligned.
5. Simulation and integration surfaces retained: aligned.

## Rollout and Backward Compatibility
1. Legacy analytics/reporting compatibility in lotus-core is intentionally removed.
2. Consumers must integrate with owning services (`lotus-performance`, `lotus-risk`, `lotus-report`) and supported core integration contracts.

## Open Questions
1. Should additional static dependency guards be added to enforce boundary layering at package-import level?
2. Should cross-repo ownership checks be elevated to platform-wide CI policy gates?

## Next Actions
1. Continue cross-repo governance hardening under existing delta backlog (`RFC-035-D01`, related items).
2. Keep contract drift checks in CI for query and ingestion OpenAPI surfaces.
