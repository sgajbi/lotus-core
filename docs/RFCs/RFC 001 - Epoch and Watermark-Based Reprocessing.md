# RFC 001 - Epoch and Watermark-Based Reprocessing

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | Historical baseline RFC (date not recorded in file) |
| Last Updated | 2026-03-04 |
| Owners | lotus-core calculators and platform data pipeline |
| Depends On | None |
| Extended By | RFC 018, RFC 019, RFC 065, RFC 066 |
| Related Standards | `docs/standards/durability-consistency.md`, `docs/standards/rfc-traceability.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 001 is the foundational architecture for deterministic reprocessing in lotus-core.
It introduced:
1. Explicit per-key state (`portfolio_id`, `security_id`) in `position_state`.
2. Epoch-based version fencing to prevent stale-message corruption.
3. Watermark-based deterministic backlog advancement controlled by schedulers.

This RFC remains architecturally valid and is the base contract for later hardening RFCs.

## Original Requested Requirements (Preserved)

The original RFC requested these core design outcomes:
1. Replace implicit, race-prone recalculation choreography with explicit `epoch` + `watermark` state.
2. Add `position_state` as the source of truth for key lifecycle (`CURRENT`, `REPROCESSING`), epoch, and progress.
3. Add `epoch` to versioned historical tables and include epoch in uniqueness semantics.
4. Define deterministic reprocessing flows:
   - back-dated transaction flow with epoch increment and replay
   - back-dated price flow with watermark reset and scheduler-driven rebuild
5. Make `ValuationScheduler` the sole authority for watermark advancement and valuation backfill.
6. Enforce concurrency correctness through epoch fencing in all reprocessing-aware consumers.
7. Ensure query APIs read only from current epoch data and optionally expose reprocessing status.
8. Provide observability for active reprocessing keys, lag, and dropped stale messages.
9. Remove legacy recalculation architecture in favor of epoch/watermark model.

## Current Implementation Reality

The core RFC 001 model is implemented and actively used.

1. `position_state` remains the source of truth for `epoch`, `watermark_date`, and reprocessing `status`.
2. Epoch fencing is centralized through reusable `EpochFencer`.
3. Watermark advancement and backfill orchestration are scheduler-driven.
4. Query reads are epoch-fenced to current state and expose reprocessing visibility.
5. Rapid and atomic reprocessing behavior is covered by integration and E2E tests.

Evidence:
- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing.py`
- `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
- `src/services/query_service/app/repositories/position_repository.py`
- `tests/e2e/test_reprocessing_workflow.py`
- `tests/e2e/test_rapid_reprocessing.py`
- `tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Evidence |
| --- | --- | --- |
| Explicit per-key state (`epoch`, `watermark_date`, status) | Implemented in canonical state repository/model | `position_state_repository.py`; `database_models.py` |
| Epoch versioning on historical outputs | Implemented across core event/data paths | `database_models.py`; reprocessing/event consumers |
| Back-dated transaction triggers epoch bump + replay | Implemented in position calculator with outbox replay | `position_logic.py`; `test_reprocessing_workflow.py` |
| Back-dated price triggers watermark reset and backfill | Implemented via valuation pipeline and scheduler flows | `valuation_scheduler.py`; ADR/RFC extension paths |
| Scheduler-only watermark advancement | Implemented in valuation scheduler orchestration | `valuation_scheduler.py`; valuation scheduler tests |
| Epoch fencing for stale messages | Implemented through shared `EpochFencer` utility | `reprocessing.py`; `test_reprocessing.py` |
| Query reads fenced to active epoch | Implemented in query repositories for versioned state reads | `query_service/app/repositories/position_repository.py` |
| Reprocessing observability | Implemented via operations APIs/metrics and test coverage | `operations.py`; e2e reliability/reprocessing tests |

## Design Reasoning and Trade-offs

1. **Why epoch fencing**: It gives deterministic safety under replay and race conditions where strict global ordering is not feasible.
2. **Why per-key watermark**: It localizes recovery progress to impacted keys and avoids platform-wide rollback/recompute.
3. **Why scheduler-owned advancement**: A single authority avoids split-brain progress updates across workers.
4. **Trade-off**: Reprocessing increases write amplification for affected keys, but dramatically improves correctness and auditability.

## Deterministic Invariants and Processing Algorithm

### Core invariants
For each key `k = (portfolio_id, security_id)`:
1. **Epoch monotonicity**:
   `epoch(k, t+1) >= epoch(k, t)`
2. **Snapshot uniqueness by epoch**:
   a snapshot row is uniquely identified by `(portfolio_id, security_id, date, epoch)`
3. **Current-read correctness**:
   query-path reads for key `k` are restricted to `epoch = max_epoch(k)`
4. **Stale-event safety**:
   if event epoch `< current epoch(k)`, event is discarded and must not mutate state
5. **Watermark monotonic advancement under current epoch**:
   scheduler may move `watermark_date(k)` forward only after required inputs for the next date window are satisfied

### Processing algorithm (high-level)
1. Receive event for key `k`.
2. Resolve or create `position_state(k)` and evaluate epoch fence.
3. If stale:
   - record observability signal
   - return without mutation.
4. If back-dated transaction requiring replay:
   - increment `epoch(k)`, reset watermark
   - re-emit historical stream + triggering event under new epoch
   - process in deterministic order.
5. Persist snapshots/history tagged with active epoch.
6. Scheduler advances watermark and publishes valuation/timeseries work only for the active epoch.

### Why this is stronger than the original baseline wording
1. The original RFC described the conceptual model; current implementation codifies reusable fencing primitives (`EpochFencer`) and durable job-based reprocessing controls.
2. The implementation now has explicit atomicity/recovery coverage proving no partial epoch mutation on failure paths.
3. Operational controls (queue health, capacity and backlog visibility) make the model production-governable at institutional scale.

## Gap Assessment

The original RFC 001 text is directionally correct but did not reflect later hardening decisions:

1. Price-trigger fan-out now uses durable queue patterns (`reprocessing_jobs`) and worker execution, not only direct fan-out logic.
2. Atomic replay hardening and resilience controls were formalized later (RFC 018 + ADR 002).
3. Epoch fencing implementation details were standardized later (RFC 019).

These are evolutions of RFC 001, not contradictions.

## Deviations and Evolution Since Original RFC

1. High-volume fan-out is now durability-first (`reprocessing_jobs` + worker model) instead of naive immediate fan-out.
2. Operational maturity and institutional controls were formalized later (RFC 065/066), extending this base contract.
3. Epoch-fencing patterns were standardized and enforced as a reusable primitive in later RFCs/standards.

## Proposed Changes

This update re-documents RFC 001 as a stable foundational contract and explicitly links later hardening layers:

1. Keep RFC 001 as the base deterministic model.
2. Treat RFC 018, RFC 019, RFC 065, and RFC 066 as implementation hardening/extensions.
3. Preserve terminology consistency: `epoch`, `watermark_date`, `REPROCESSING`, `CURRENT`.

## Test and Validation Evidence

1. Epoch fencing behavior and stale-message discard path:
   - `tests/unit/libs/portfolio-common/test_reprocessing.py`
2. Back-dated transaction reprocessing and epoch increment:
   - `tests/e2e/test_reprocessing_workflow.py`
3. Rapid chained reprocessing (0 -> 1 -> 2):
   - `tests/e2e/test_rapid_reprocessing.py`
4. Atomicity under outbox failure:
   - `tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py`

## Original Acceptance Criteria Alignment

Original intent is materially satisfied:
1. Legacy recalculation model replaced by epoch/watermark-driven reprocessing architecture.
2. Position calculator no longer directly orchestrates valuation recalculation as old model required.
3. Back-dated transaction/price paths trigger deterministic recovery behavior.
4. Scheduler-driven valuation/backfill model is active.
5. API read paths are epoch-aware for correctness during/after reprocessing.
6. End-to-end reprocessing regression tests exist and are passing in repo baseline.

## Rollout and Backward Compatibility

No API-breaking changes are introduced by this documentation refresh.
This RFC remains backward compatible as a foundational architectural contract.

## Open Questions

1. Should a concise "RFC 001 invariants" section be added to `docs/standards/` to provide a single enforcement checklist for CI and operations?

## Next Actions

1. Keep RFC 001 classification as `Fully implemented and aligned`.
2. Treat policy/capacity operating contracts from RFC 065 and RFC 066 as regression-monitoring scope (implemented, must stay green).
3. Keep EpochFencer usage under periodic review for new consumers; current baseline is implemented and test-backed.
