# RFC 024 - Ensure Atomic Portfolio Time-Series Aggregation

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-05 |
| Owners | `timeseries_generator_service`, `position_valuation_calculator` |
| Depends On | RFC 003, RFC 018 |
| Scope | Deterministic/complete-input gating for portfolio-level timeseries aggregation |

## Executive Summary

RFC 024 identified a correctness risk: portfolio aggregation can run before all position-level inputs for the day are present.
The RFC proposed a manifest-based completeness gate.

Implemented approach uses an equivalent deterministic count contract in claim logic:
1. For each pending job, expected inputs are counted from `daily_position_snapshots` for portfolio/date/current-epoch.
2. Actual transformed inputs are counted from `position_timeseries` for portfolio/date/current-epoch.
3. Job is claimable only when counts are equal and non-zero, in addition to sequential day rules.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 024 requested:
1. Introduce `daily_aggregation_manifest` table with expected input count by portfolio/day.
2. Have upstream scheduler create/maintain manifest entries.
3. Make aggregation job claiming depend on manifest completeness checks.
4. Add pending-manifest observability metric.
5. Add unit/integration/E2E tests for atomic aggregation guarantee.

## Current Implementation Reality

Implemented today:
1. Aggregation jobs are stateful and claimed atomically with eligibility rules.
2. Eligibility requires prior-day portfolio timeseries existence or first-job condition.
3. Integration tests verify sequential claim behavior for day ordering.

Not implemented exactly as originally proposed:
1. No dedicated `daily_aggregation_manifest` table was introduced.
2. No manifest-pending metric was introduced under that naming.

Implemented equivalently:
1. Deterministic completeness gating is now enforced directly in claim query using authoritative table counts.
2. Integration tests validate that incomplete same-day inputs block claims.

Evidence:
- `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
- `tests/integration/services/timeseries_generator_service/test_timeseries_repository_integration.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `docs/features/timeseries_generator/01_Feature_Timeseries_Generator_Overview.md`
- `docs/features/timeseries_generator/04_Operations_Troubleshooting_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Manifest table for expected input count | Not implemented as a separate table (superseded by equivalent count contract) | `database_models.py` (no manifest model) |
| Upstream manifest creation | Not applicable under equivalent design | claim-query count contract |
| Claim based on completeness count | Implemented (snapshot count must equal position-timeseries count) | `timeseries_repository.py`; integration tests |
| Pending-manifest metric | Not implemented under manifest naming | monitoring + service paths |
| Atomic completeness validation tests | Implemented | `test_timeseries_repository_integration.py` |

## Design Reasoning and Trade-offs

1. The previous sequential-only gate improved ordering but was insufficient for completeness.
2. The implemented count-based gate provides deterministic completeness guarantees without adding new manifest table lifecycle complexity.

Trade-off:
- Full manifest implementation adds schema and orchestration complexity, but materially strengthens correctness and auditability.

## Gap Assessment

1. No remaining blocking correctness gap for RFC-024 acceptance criteria.

## Deviations and Evolution Since Original RFC

1. System evolved from sequencing-only safeguards to sequencing + deterministic completeness gate.
2. Original manifest-table approach was replaced with an equivalent in-query count contract.

## Proposed Changes

1. Keep the equivalent count-based completeness contract as the active implementation pattern.
2. Maintain integration coverage proving portfolio-day aggregation waits for full position input set.

## Test and Validation Evidence

1. Completeness and sequential eligibility verification:
   - `tests/integration/services/timeseries_generator_service/test_timeseries_repository_integration.py`
2. Repository claim logic under current design:
   - `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`

## Original Acceptance Criteria Alignment

Aligned:
1. Stateful aggregation job orchestration exists.
2. Atomic completeness gating is delivered via deterministic count contract and integration tests.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should a dedicated completeness metric be added to expose blocked jobs by missing-input count for faster operations triage?

## Next Actions

1. Keep RFC 024 marked implemented with equivalent deterministic completeness contract.
2. Maintain integration regression coverage for claim gating behavior.
