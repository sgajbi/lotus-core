# RFC 005 - Enhance Unit Test Robustness and Code Quality

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-08-29 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core engineering |
| Depends On | RFC 003, RFC 004 |
| Related Standards | `docs/standards/enterprise-readiness.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 005 was a focused quality-hardening slice:
1. Fix a repository defect surfaced by unit tests.
2. Add missing test coverage for valuation scheduler dispatch path.
3. Add missing test coverage for valuation consumer unexpected-failure behavior.

The requested fixes and test additions are implemented.

## Original Requested Requirements (Preserved)

The original RFC requested:
1. Fix `PositionStateRepository.bulk_update_states` row-count defect causing failing tests.
2. Add a unit test for valuation scheduler dispatching claimed jobs to Kafka.
3. Add a unit test for valuation consumer generic exception path (`FAILED` + DLQ behavior).
4. Improve confidence in these critical control paths through explicit coverage.

## Current Implementation Reality

Implemented outcomes:
1. `bulk_update_states` updates are handled correctly and covered by tests.
2. Valuation scheduler dispatch path is unit-tested.
3. Valuation consumer unexpected-error path is unit-tested and exercises failure handling.

Evidence:
- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
- `tests/unit/libs/portfolio-common/test_position_state_repository.py`
- `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
- `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Evidence |
| --- | --- | --- |
| Fix bulk update row-count behavior | Repository implementation and tests now stable | `position_state_repository.py`; repo unit tests |
| Add scheduler dispatch unit test | Dispatch path covered in scheduler tests | `test_valuation_scheduler.py` |
| Add consumer unexpected-error unit test | Failure status + DLQ behavior covered | `test_valuation_consumer.py` |
| Raise confidence in critical paths | Coverage exists on the previously missing paths | same test modules |

## Design Reasoning and Trade-offs

1. **Why this RFC mattered**: small defects in orchestration and status paths can create high operational noise.
2. **Why test-first hardening**: these paths are control-plane critical; regressions are costly and hard to diagnose late.
3. **Trade-off**: added tests increase maintenance overhead slightly but greatly improve regression signal quality.

## Gap Assessment

No open gap remains tied to RFC 005 scope.

## Deviations and Evolution Since Original RFC

1. Scope stayed intentionally narrow and tactical.
2. Broader test-strategy evolution now continues under later RFC waves (e.g., RFC 010, RFC 028, RFC 050+).

## Proposed Changes

1. Keep RFC 005 as completed historical quality baseline.
2. Do not reopen scope unless regressions indicate renewed risk in these same paths.

## Test and Validation Evidence

1. Position state repository behavior:
   - `tests/unit/libs/portfolio-common/test_position_state_repository.py`
2. Scheduler dispatch behavior:
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
3. Consumer unexpected-failure behavior:
   - `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`

## Original Acceptance Criteria Alignment

Original acceptance intent is satisfied:
1. Previously failing `bulk_update_states` path is corrected and covered.
2. Missing scheduler dispatch test exists.
3. Missing consumer failure-path test exists.
4. Quality signal for targeted modules improved.

## Rollout and Backward Compatibility

Documentation retrofit only; no runtime contract change.

## Open Questions

1. Should micro-RFC quality slices be systematically grouped into a quality ledger to reduce future traceability overhead?

## Next Actions

1. Keep RFC 005 classification as `Fully implemented and aligned`.
2. Treat this RFC as historical evidence of targeted hardening completion.
