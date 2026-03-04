# RFC 034 - API Contract Decomposition and Vocabulary Alignment

| Metadata | Value |
| --- | --- |
| Status | Deprecated |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | `query-service`, API governance |
| Depends On | RFC 012, RFC 039, RFC 040, RFC 056, RFC 057, RFC 067 stream |
| Scope | Decompose oversized API contracts and enforce canonical vocabulary discipline |

## Executive Summary

RFC 034 originally centered decomposition around a retained in-core `review` orchestration endpoint.
That assumption is no longer valid in current architecture:
1. `POST /portfolios/{portfolio_id}/review` is removed from active lotus-core ownership.
2. Reporting/review orchestration is intentionally de-owned (RFC 056, RFC 057) and redirected to lotus-report.
3. Decomposition and vocabulary goals still matter, but execution happened through later RFCs and API surface evolution.

Classification: `Outdated (requires revision)`.

## Original Requested Requirements (Preserved)

Original RFC 034 requested:
1. Keep review as a composed convenience API.
2. Decompose domain concerns into smaller endpoint contracts.
3. Enforce canonical vocabulary and DTO-level descriptions/examples.
4. Support gateway-first composition without spreading business semantics across clients.

## Current Implementation Reality

Implemented/evolved:
1. Legacy review endpoint is removed and returns explicit migration guidance (`410 Gone` path behavior).
2. Query-service now exposes decomposed contract domains (`positions`, `transactions`, `operations`, `integration`, `analytics_inputs`, `lookups`, `simulation`) rather than a monolithic review payload.
3. Vocabulary governance artifacts exist and include endpoint/field coverage for integration and lookup contracts.
4. OpenAPI contract tests validate active route inventory and prevent legacy endpoint resurrection.

No longer aligned with current system:
1. Recommendation to keep in-core review orchestration as the decomposition anchor.
2. Assumption that decomposition roadmap is centered on review sections (`overview`, `risk`, `activity`) inside lotus-core.

Evidence:
- `src/services/query_service/app/main.py`
- `src/services/query_service/app/routers/legacy_gone.py`
- `tests/integration/services/query_service/test_main_app.py`
- `tests/e2e/test_review_pipeline.py`
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Keep in-core review orchestration | Deprecated and removed from active ownership | RFC 056/057; legacy-gone handling; OpenAPI tests |
| Decompose oversized query contracts | Implemented through split routers and dedicated contract families | query-service router inventory in `main.py` |
| Canonical vocabulary enforcement | Implemented as structured API vocabulary artifact + contract governance flow | `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` |
| DTO field descriptions/examples | Implemented broadly for current integration and ingestion surfaces | integration/capabilities/upload DTOs and router descriptions |

## Design Reasoning and Trade-offs

1. Removing the review aggregate from lotus-core reduced ownership ambiguity and prevented cross-domain coupling with reporting services.
2. Decomposition into bounded contracts improved API testability and route-level governance.
3. Vocabulary governance in repository standards reduced uncontrolled synonym drift.

Trade-off:
- Consumers that previously depended on review-style assembled payloads now compose data through gateway/reporting layers rather than lotus-core directly.

## Gap Assessment

Remaining delta:
1. RFC 034 text itself is now stale and should be superseded by a current-era API decomposition/vocabulary governance RFC that references active endpoints only.

## Deviations and Evolution Since Original RFC

1. The design pivot moved from “retain review but decompose around it” to “retire review and keep lotus-core as canonical data and integration contract provider.”
2. Lookup and integration contract maturation (RFC 039-044) became the practical decomposition path.

## Proposed Changes

1. Keep RFC 034 as a historical record but mark it `Deprecated`.
2. Track replacement with a fresh decomposition-and-vocabulary governance RFC aligned to post-RFC-057 architecture.

## Test and Validation Evidence

1. Legacy endpoint exclusion and OpenAPI checks:
   - `tests/integration/services/query_service/test_main_app.py`
2. Legacy review migration behavior:
   - `tests/e2e/test_review_pipeline.py`
3. Active decomposed router composition:
   - `src/services/query_service/app/main.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Decomposition and vocabulary outcomes are materially present.
2. The central review-preservation design is obsolete and intentionally not implemented.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should the replacement RFC be authored as lotus-core-only governance, or as a cross-repo contract master RFC with lotus-platform ownership?

## Next Actions

1. Draft successor RFC for active decomposition/vocabulary governance model.
2. Keep this RFC as deprecated historical context only.
