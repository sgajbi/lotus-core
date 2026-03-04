# RFC 004 - Make Reprocessing Deterministic

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-02 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core position calculator and valuation pipeline |
| Depends On | RFC 001 |
| Related Standards | `docs/standards/durability-consistency.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 004 closed a correctness race in back-dated transaction detection.
The key change was to compute `effective_completed_date` as the later of:
1. `position_state.watermark_date`
2. latest completed `daily_position_snapshot` date for the current epoch.

This made reprocessing triggers deterministic even when scheduler watermark advancement lags.

## Original Requested Requirements (Preserved)

The original RFC requested:
1. Eliminate race condition caused by relying only on watermark date.
2. Add repository support to read latest completed snapshot date for a key/epoch.
3. Trigger reprocessing when `transaction_date < effective_completed_date`.
4. Keep replay atomic (epoch bump + outbox replay) and preserve epoch propagation.
5. Standardize consumer epoch fencing for replay safety.
6. Validate behavior through unit, integration, and e2e reprocessing tests.
7. Keep docs synchronized with the new detection method.

## Current Implementation Reality

Implemented behavior matches RFC intent:
1. Position calculator computes `effective_completed_date = max(watermark_date, latest_snapshot_date)`.
2. Repository exposes latest completed snapshot date lookup.
3. Reprocessing trigger path is atomic and replay is staged through outbox with new epoch.
4. Replay events carry epoch and downstream paths use fencing semantics.

Evidence:
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `src/services/calculators/position_calculator/app/repositories/position_repository.py`
- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
- `tests/integration/services/calculators/position_calculator/test_int_position_calc_repo.py`
- `tests/e2e/test_reprocessing_workflow.py`
- `tests/e2e/test_rapid_reprocessing.py`
- `docs/features/reprocessing_engine/02_Triggers_and_Flows.md`
- `docs/features/position_calculator/03_Methodology_Guide.md`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Evidence |
| --- | --- | --- |
| Replace watermark-only detection | Uses effective completed date with snapshot fallback | `position_logic.py` |
| Add latest snapshot date accessor | Implemented on position repository | `position_repository.py` |
| Deterministic back-dated trigger | Trigger condition compares tx date with effective completed date | `position_logic.py`; unit tests |
| Preserve atomic replay behavior | Epoch bump + outbox replay remains in one flow | `position_logic.py`; reprocessing e2e |
| Preserve epoch propagation and fencing | Replayed events carry epoch and are fenced | `reprocessing.py`; consumer paths/tests |
| Validate with broad tests | Unit/integration/e2e suites present | listed test files |
| Keep methodology docs updated | Detection method documented in feature docs | `docs/features/...` files above |

## Design Reasoning and Trade-offs

1. **Why snapshot-aware detection**: snapshot persistence is closer to completed work truth than scheduler watermark timing.
2. **Why max(watermark, snapshot)**: keeps scheduler progress authoritative where ahead, but protects when scheduler lags.
3. **Why keep epoch fencing unchanged**: detection fix is meaningful only if stale replay messages remain safely discardable.
4. **Trade-off**: one additional indexed read per event for correctness-critical determinism.

## Gap Assessment

No material implementation gap found for RFC 004 core commitments.

## Deviations and Evolution Since Original RFC

1. Consumer fencing standardization matured further under later RFCs (especially RFC 019).
2. Operational readiness/scale controls added in RFC 065/066 extend but do not alter RFC 004 correctness model.

## Proposed Changes

1. Keep RFC 004 as implemented deterministic detection baseline.
2. Keep regression focus on reprocessing determinism and epoch-safe replay.

## Test and Validation Evidence

1. Effective completed date and trigger logic:
   - `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
2. Snapshot lookup integration behavior:
   - `tests/integration/services/calculators/position_calculator/test_int_position_calc_repo.py`
3. End-to-end deterministic reprocessing:
   - `tests/e2e/test_reprocessing_workflow.py`
   - `tests/e2e/test_rapid_reprocessing.py`

## Original Acceptance Criteria Alignment

Original acceptance criteria are satisfied:
1. Repository method exists for latest snapshot lookup.
2. Calculator uses effective completed date logic.
3. Replay events include epoch and reprocessing flow remains deterministic.
4. Relevant consumers preserve fencing behavior.
5. Unit/integration/e2e tests cover critical flows.
6. Methodology/flow docs reflect implemented detection approach.

## Rollout and Backward Compatibility

No API contract break introduced by this documentation retrofit.

## Open Questions

1. Should deterministic replay-order checks become explicit production runbook controls?

## Next Actions

1. Keep RFC 004 classification as `Fully implemented and aligned`.
2. Continue regression monitoring through integration and e2e suites.
