# RFC 024 - Ensure Atomic Portfolio Time-Series Aggregation

| Metadata | Value |
| --- | --- |
| Status | Partially Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-04 |
| Owners | `timeseries_generator_service`, `position_valuation_calculator` |
| Depends On | RFC 003, RFC 018 |
| Scope | Deterministic/complete-input gating for portfolio-level timeseries aggregation |

## Executive Summary

RFC 024 identified a correctness risk: portfolio aggregation can run before all position-level inputs for the day are present.
The RFC proposed a manifest-based completeness gate (`daily_aggregation_manifest` + expected count checks).

Current implementation includes a partial mitigation (sequential day-eligibility gating) but not the manifest design.
Classification is therefore `Partially implemented (requires enhancement)`.

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

Not implemented from RFC 024 proposal:
1. No `daily_aggregation_manifest` model or migration.
2. No manifest expected-count gating in claim query.
3. No `timeseries_aggregation_pending_manifests` metric.
4. Feature docs still document unresolved aggregation integrity gap.

Evidence:
- `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
- `tests/integration/services/timeseries_generator_service/test_timeseries_repository_integration.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `docs/features/timeseries_generator/01_Feature_Timeseries_Generator_Overview.md`
- `docs/features/timeseries_generator/04_Operations_Troubleshooting_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Manifest table for expected input count | Not implemented | `database_models.py` (no manifest model) |
| Upstream manifest creation | Not implemented | valuation paths + schema review |
| Claim based on completeness count | Partially addressed by sequential-day eligibility only | `timeseries_repository.py`; integration tests |
| Pending-manifest metric | Not implemented | monitoring + service paths |
| Atomic completeness validation tests | Partial sequencing tests only | `test_timeseries_repository_integration.py` |

## Design Reasoning and Trade-offs

1. Current sequential claim rule improves ordering but does not prove all same-day position inputs are present.
2. Manifest-based gating remains the stronger correctness design when completeness must be guaranteed explicitly.

Trade-off:
- Full manifest implementation adds schema and orchestration complexity, but materially strengthens correctness and auditability.

## Gap Assessment

Remaining high-value gap:
1. Implement explicit completeness gating (manifest or equivalent deterministic count contract) before claiming aggregation jobs.

## Deviations and Evolution Since Original RFC

1. System evolved to include stronger job-state handling and sequencing safeguards.
2. Original RFC’s manifest architecture was not adopted yet; docs still acknowledge residual integrity risk.

## Proposed Changes

1. Implement RFC 024 manifest design (or an equivalent explicit completeness contract) and retire known gap from feature docs.
2. Add integration/E2E test that proves portfolio-day aggregation waits for full position input set.

## Test and Validation Evidence

1. Current sequential-eligibility verification:
   - `tests/integration/services/timeseries_generator_service/test_timeseries_repository_integration.py`
2. Repository claim logic under current design:
   - `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Stateful aggregation job orchestration exists.
2. Manifest-based atomic completeness gate and associated observability/tests are not yet delivered.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should completeness gating use proposed manifest table or a lighter-weight derived-count contract with equivalent deterministic guarantees?
2. Which service should own expected-count generation in the final design (`position_valuation_calculator` vs `timeseries_generator_service`)?

## Next Actions

1. Track manifest/completeness implementation as an open delta in `RFC-DELTA-BACKLOG.md`.
2. Keep current sequential mitigation while implementing full correctness gate.
