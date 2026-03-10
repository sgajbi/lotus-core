# RFC 012 - Portfolio Review API

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-31 |
| Last Updated | 2026-03-04 |
| Owners | lotus-report (authoritative owner for review/report APIs) |
| Depends On | RFC 056, RFC 057 |
| Scope | Archived from `lotus-core`; endpoint ownership moved to `lotus-report` |

## Executive Summary

RFC 012 originally proposed a consolidated `POST /portfolios/{portfolio_id}/review` orchestration endpoint in lotus-core.
That capability has been de-owned and migrated to lotus-report.

This file remains as a comprehensive migration record, not an active implementation RFC for lotus-core.

## Original Requested Requirements (Preserved)

Original RFC 012 requested:
1. A single review endpoint composing summary/performance/risk/holdings/transaction sections.
2. Epoch-consistent orchestration across all sections in one request scope.
3. Async fan-out orchestration internally (`asyncio.gather`) for latency efficiency.
4. Standardized DTO contract and report section output.
5. Observability for report-generation latency and sub-call timing.

## Current Implementation Reality

1. Lotus-core review endpoint is hard-disabled and returns `410 Gone` with migration guidance.
2. Migration target is lotus-report.
3. No active review router/service remains in lotus-core query service.

Evidence:
- `docs/RFCs/RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints.md`
- `tests/e2e/test_review_pipeline.py`
- `tests/e2e/test_complex_portfolio_lifecycle.py`
- `src/services/query_service/app/main.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| In-core review orchestration endpoint | De-owned and removed from active capability | RFC 056; router set in `main.py` |
| Epoch-consistent section orchestration | Responsibility moved to lotus-report | migration decision and 410 tests |
| Review DTO and review router in-core | Not active in current query-service | router listing in repo |
| Review latency observability in-core | Not applicable after de-ownership | no active review path |
| Migration guidance for callers | Implemented via disabled-route behavior contract and shared E2E assertions | e2e review tests; shared assertions |

## Design Reasoning and Trade-offs

1. **Why move ownership**: reporting-style aggregation aligns better with lotus-report domain boundaries.
2. **Why explicit 410 behavior**: deterministic migration guidance is safer than silent removal.
3. **Trade-off**: callers must migrate routes; temporary integration friction is accepted for clearer architecture.

## Gap Assessment

No lotus-core implementation gap remains for RFC 012 itself.
Remaining work belongs to lotus-report and consuming applications.

## Deviations and Evolution Since Original RFC

1. Original in-core orchestration plan was superseded by service decomposition RFCs.
2. Endpoint remained visible only as migration stub behavior during transition.
3. Lotus-core focus shifted toward canonical data and integration contracts rather than assembled review/report APIs.

## Proposed Changes

1. Keep RFC 012 archived with full migration rationale.
2. Keep all active review API evolution in lotus-report.

## Test and Validation Evidence

1. Hard-disabled migration behavior:
   - `tests/e2e/test_review_pipeline.py`
   - `tests/e2e/test_complex_portfolio_lifecycle.py`
2. Disabled-route behavior policy:
   - `tests/e2e/assertions.py`

## Original Acceptance Criteria Alignment

Original in-core acceptance criteria are no longer applicable due to ownership shift. Current lotus-core acceptance is migration behavior correctness and contractual redirection.

## Rollout and Backward Compatibility

No runtime behavior change from this documentation retrofit.

## Open Questions

1. Are any internal consumers still using the legacy lotus-core review route and relying on migration behavior?

## Next Actions

1. Keep this RFC as archived compatibility pointer.
2. Continue review/report API ownership in lotus-report.
3. Ensure dependent apps consume lotus-report endpoint contracts.
