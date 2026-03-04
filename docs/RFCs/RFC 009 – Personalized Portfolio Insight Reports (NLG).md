# RFC 009 - Personalized Portfolio Insight Reports (NLG)

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | lotus-report and AI/reporting domain services (outside lotus-core) |
| Depends On | RFC 012 (historical dependency), cross-app architecture decisions |
| Scope | Archived from `lotus-core`; not implemented in this repository |

## Executive Summary

RFC 009 proposed an asynchronous AI-native insight pipeline with:
1. query-service insight job APIs
2. dedicated insight-report microservice
3. persisted insight jobs/reports
4. constrained narrative generation based on structured observations.

This architecture is not implemented in lotus-core and is out of current lotus-core bounded ownership.

## Original Requested Requirements (Preserved)

Original RFC 009 requested:
1. `POST /portfolios/{portfolio_id}/insights` + polling endpoint for async job lifecycle.
2. New `insight-report-service` consuming queued work and calling review data APIs.
3. Multi-stage deterministic observation generation before LLM synthesis.
4. Persisted audit tables (`insight_generation_jobs`, `insight_reports`) with explainability references.
5. Model-agnostic deployment with privacy controls and operational metrics.

## Current Implementation Reality

1. No insight-report service exists in this repository.
2. No insight job/report schema exists in lotus-core migrations.
3. No `/insights` query-service endpoints exist in lotus-core.
4. Upstream review/report orchestration assumed by RFC 009 has moved out of lotus-core ownership.

Evidence:
- `src/services/query_service/app/main.py` (registered routers do not include insights APIs)
- `src/services/query_service/app/routers/`
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`
- `tests/e2e/test_review_pipeline.py`
- repository search shows insight artifacts only in RFC text

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Async insights endpoint surface | Not implemented | `query_service/main.py`; router list |
| Dedicated insight-report-service | Not in repo | repo structure/search |
| Insight persistence tables | Not in migrations | alembic search results |
| Review-driven input flow | Review/report APIs de-owned from lotus-core | RFC 056; review e2e 410 tests |
| Operational metrics for insight flow | Not applicable in lotus-core scope | no insight runtime artifacts |

## Design Reasoning and Trade-offs

1. **Why archive in lotus-core**: capability belongs with reporting/AI domain ownership, not core data processing services.
2. **Why keep RFC here**: preserves history and integration intent for cross-app reference.
3. **Trade-off**: splitting ownership requires stronger contract governance between core data APIs and insight consumers.

## Gap Assessment

No lotus-core implementation gap is tracked for RFC 009 itself because it is out of scope for this repository.

## Deviations and Evolution Since Original RFC

1. Reporting/review capabilities moved away from lotus-core.
2. AI/NLG service responsibilities were not onboarded into lotus-core architecture.
3. Lotus-core evolved toward canonical data and integration contracts, not advisor-facing narrative services.

## Proposed Changes

1. Keep RFC 009 archived in lotus-core with full migration rationale.
2. Re-home active insight-report design and delivery to authoritative reporting/AI service repository.

## Test and Validation Evidence

1. Absence evidence:
   - no insights routers or migration artifacts in lotus-core
2. Ownership migration context:
   - RFC 056 and review endpoint migration tests

## Original Acceptance Criteria Alignment

Original acceptance criteria are not met in lotus-core because implementation scope moved out. This is a deliberate ownership decision, not an untracked implementation failure in current repo scope.

## Rollout and Backward Compatibility

No lotus-core runtime change from this documentation retrofit.

## Open Questions

1. Which repository is now the canonical home for this insight-report RFC lineage and acceptance criteria?

## Next Actions

1. Keep this RFC as historical context in lotus-core.
2. Re-home active insight/NLG RFC and roadmap to reporting/AI service repo.
3. Keep lotus-core focused on canonical data contracts consumed by downstream reporting/AI services.
