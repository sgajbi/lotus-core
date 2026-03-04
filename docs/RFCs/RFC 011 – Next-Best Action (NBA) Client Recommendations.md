# RFC 011 - Next-Best Action (NBA) Client Recommendations

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | NBA/recommendation service domain (outside lotus-core) |
| Depends On | RFC 012 (historical dependency) |
| Scope | Archived from `lotus-core`; not implemented in this repository |

## Executive Summary

RFC 011 proposed an asynchronous recommendation intelligence platform (signals, scoring, rationale generation, feedback loops).
That scope was never implemented inside lotus-core and does not fit current lotus-core domain ownership.

## Original Requested Requirements (Preserved)

Original RFC 011 requested:
1. New async NBA job APIs (`/nba-jobs`) and feedback endpoint.
2. Dedicated `nba-service` with queue-driven generation pipeline.
3. Signal detection + ML ranking + constrained narrative generation.
4. Persistence for jobs/recommendations/feedback.
5. Portfolio context enrichment fields for personalization.
6. Observability for throughput, latency, and feedback outcomes.

## Current Implementation Reality

1. No `nba-service` exists in this repository.
2. No NBA endpoints are exposed by lotus-core query-service.
3. No NBA tables are present in lotus-core migrations.
4. Dependencies on in-core review/report orchestration are stale because reporting ownership moved to lotus-report.

Evidence:
- `src/services/query_service/app/main.py`
- `src/services/query_service/app/routers/`
- repository-wide search for `nba_jobs` / `nba_feedback` / NBA routes
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Async NBA endpoints | Not implemented | query-service routers/main |
| Dedicated NBA service | Not in repo | repo structure/search |
| NBA persistence schema | Not in migrations | alembic search |
| Feedback ingestion endpoint | Not implemented | query-service routers |
| Personalized context enrichment for NBA | Not implemented in this RFC scope in-core | schema/code search |

## Design Reasoning and Trade-offs

1. **Why archive here**: NBA belongs to recommendation/intelligence service ownership, not core transaction/ledger processing.
2. **Why keep the RFC file**: preserves lineage and integration intent for cross-app architecture.
3. **Trade-off**: migration to separate service requires explicit data-contract governance and tighter cross-repo alignment.

## Gap Assessment

No actionable lotus-core implementation gap is tracked for RFC 011 because capability ownership is outside this repository.

## Deviations and Evolution Since Original RFC

1. Lotus-core service boundaries were tightened around canonical ingestion, processing, and integration contracts.
2. Reporting and advisor-facing orchestration moved away from lotus-core.
3. NBA pipeline scope remained outside lotus-core implementation path.

## Proposed Changes

1. Keep RFC 011 archived in lotus-core with full rationale.
2. Re-home active NBA design and delivery to authoritative recommendation service repository.

## Test and Validation Evidence

1. Absence evidence in lotus-core runtime/migrations:
   - query-service routers/main, alembic schema scan
2. Ownership migration context:
   - RFC 056 and related de-ownership RFCs

## Original Acceptance Criteria Alignment

Original acceptance criteria are not met in lotus-core by design, because ownership moved out of repo scope.

## Rollout and Backward Compatibility

No lotus-core runtime change from this documentation retrofit.

## Open Questions

1. Which repository is canonical for NBA RFC ownership and acceptance tracking?

## Next Actions

1. Keep this RFC as historical context in lotus-core.
2. Re-home active NBA RFC and roadmap to recommendation-service repository.
3. Maintain lotus-core as canonical data/input contract provider for downstream intelligence services.
