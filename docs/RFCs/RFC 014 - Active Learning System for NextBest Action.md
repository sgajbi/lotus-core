# RFC 014 - Active Learning System for Next-Best Action

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Created | 2025-08-30 |
| Last Updated | 2026-03-04 |
| Owners | NBA/ML platform services (outside lotus-core) |
| Depends On | RFC 011 |
| Scope | Archived from `lotus-core`; not implemented in this repository |

## Executive Summary

RFC 014 proposed a closed-loop MLOps system for NBA model retraining (`ml-training-service`, champion/challenger lifecycle, artifact store integration).
This is outside lotus-core bounded ownership and is not implemented in this repository.

## Original Requested Requirements (Preserved)

Original RFC 014 requested:
1. Persist recommendation feature vectors and advisor feedback.
2. Build scheduled/event-driven retraining service.
3. Implement champion/challenger validation and automated promotion.
4. Version model artifacts and enable online service hot-reload.
5. Operate a full active-learning feedback loop.

## Current Implementation Reality

1. No `ml-training-service` exists in lotus-core.
2. No NBA recommendation/feedback schema in lotus-core for this pipeline.
3. No model artifact lifecycle logic in lotus-core.
4. RFC dependency scope (`nba-service`) is itself out of lotus-core scope.

Evidence:
- repository search for `nba_recommendations`, `nba_feedback`, `ml-training-service`, model artifact handling in lotus-core code/migrations
- `src/services/query_service/app/main.py` router surface

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Feature-vector persistence for NBA | Not implemented | schema/code search |
| Advisor feedback loop APIs | Not implemented | router/schema search |
| Automated retraining service | Not implemented | service search |
| Champion/challenger promotion flow | Not implemented | no MLOps pipeline code |
| Model hot-reload in serving service | Not implemented | no NBA serving in-core |

## Design Reasoning and Trade-offs

1. **Why archive in lotus-core**: this is recommendation/ML domain scope, not core transaction/ledger platform scope.
2. **Why keep reference**: preserves strategy lineage and future cross-app integration context.
3. **Trade-off**: active-learning execution must be coordinated cross-repo with explicit core data contracts.

## Gap Assessment

No actionable lotus-core implementation gap is tracked for RFC 014 itself.

## Deviations and Evolution Since Original RFC

1. Lotus-core ownership tightened around canonical data processing and integration contracts.
2. NBA and narrative/reporting domains did not land as lotus-core runtime capabilities.

## Proposed Changes

1. Keep RFC 014 archived in lotus-core.
2. Re-home active RFC and implementation tracking to the recommendation/ML service repository.

## Test and Validation Evidence

1. Absence evidence:
   - no NBA/ML training runtime, schema, or API surfaces in lotus-core.

## Original Acceptance Criteria Alignment

Original acceptance criteria are intentionally out-of-scope for lotus-core and must be validated in the destination recommendation/ML platform.

## Rollout and Backward Compatibility

No runtime change from this documentation retrofit.

## Open Questions

1. Which repository is authoritative for NBA active-learning RFC governance and acceptance tracking?

## Next Actions

1. Keep this RFC as archived historical context in lotus-core.
2. Re-home active learning roadmap to the owning recommendation/ML services repository.
