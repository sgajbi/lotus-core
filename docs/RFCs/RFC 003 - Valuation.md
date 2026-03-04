# RFC 003 - Robust, Resilient, and Scalable Valuation Pipeline

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | Historical RFC baseline (date not recorded in file) |
| Last Updated | 2026-03-04 |
| Owners | lotus-core valuation and calculator services |
| Depends On | RFC 001 |
| Related Standards | `docs/standards/scalability-availability.md`, `docs/standards/durability-consistency.md` |
| Scope | In repo (`lotus-core`) |

## Executive Summary

RFC 003 hardens valuation orchestration so the pipeline remains deterministic and operationally stable under data timing gaps and reprocessing pressure.

Core outcomes are implemented:
1. Durable valuation job lifecycle fields (`attempt_count`, `failure_reason`).
2. Position-aware backfill scheduling based on first-open-date boundaries.
3. Intelligent consumer behavior that marks expected no-position jobs as terminal skip instead of poisoning DLQ flows.

## Original Requested Requirements (Preserved)

The original RFC requested:
1. Stop treating missing-position valuation as generic retryable failure.
2. Add durable valuation job lifecycle metadata (`attempt_count`, `failure_reason`).
3. Prevent scheduler from creating valuation jobs before the position exists.
4. Distinguish terminal expected no-position scenarios from transient infrastructure failures.
5. Improve observability of valuation job outcomes and reduce operational noise.

## Current Implementation Reality

RFC 003 behavior is implemented and active.

1. Lifecycle columns exist on `portfolio_valuation_jobs`.
2. Valuation scheduler creates backfill from `max(watermark_date + 1, first_open_date)`.
3. Consumer marks missing-position cases as `SKIPPED_NO_POSITION` with failure reason and no DLQ escalation.
4. Watermark advancement remains scheduler-owned and tied to contiguous snapshot completion.

Evidence:
- `alembic/versions/b25f9ec89ae3_feat_add_lifecycle_columns_to_valuation_.py`
- `src/libs/portfolio-common/portfolio_common/database_models.py` (`PortfolioValuationJob`)
- `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
- `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
- `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation | Evidence |
| --- | --- | --- |
| Durable lifecycle fields on valuation jobs | Implemented with schema/model support | `b25f9ec89ae3...`; `database_models.py` |
| Position-aware scheduling start | Implemented using `max(watermark+1, first_open_date)` | `valuation_scheduler.py` |
| Non-retryable missing-position handling | Implemented as `SKIPPED_NO_POSITION` terminal state | `valuation_consumer.py`; consumer tests |
| Keep transient failures retry/DLQ eligible | Implemented through failure path handling | consumer tests; repository status updates |
| Reduce DLQ noise from expected data timing | Achieved by terminal skip semantics | unit tests + valuation pipeline behavior |

## Design Reasoning and Trade-offs

1. **Why position-aware scheduling**: Scheduling work before existence creates false failures and operational noise.
2. **Why explicit terminal skip state**: It preserves auditability without misclassifying expected domain conditions as incidents.
3. **Why durable lifecycle metadata**: Enables retry governance and failure forensics at job level.
4. **Trade-off**: More status semantics in job lifecycle, but significantly cleaner operations and triage.

## Gap Assessment

The original RFC text is mostly implemented but was stale in presentation:
1. It remained framed as a proposal instead of implemented contract.
2. It mixed valuation-specific scope with broader reprocessing architecture narrative that is now covered in later RFCs/ADRs.

No critical implementation gaps were identified for this RFC’s primary commitments.

## Deviations and Evolution Since Original RFC

1. Broader reprocessing scalability mechanics are now handled by later RFCs/ADRs (e.g., RFC 018, ADR 002), keeping RFC 003 focused on valuation correctness.
2. Operational expectations around job-state distributions are now stronger due to RFC 065/066 readiness posture.

## Proposed Changes

1. Keep RFC 003 as implemented valuation hardening baseline.
2. Keep subsequent large-scale queue/reprocessing fan-out evolution referenced via RFC 018 and ADR 002 (extension path, not contradiction).
3. Preserve explicit terminal handling semantics for non-retryable missing-position conditions.

## Test and Validation Evidence

1. Consumer skip semantics and terminal status behavior:
   - `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`
2. Position-aware scheduler behavior and watermark advancement:
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
3. End-to-end valuation pipeline completion:
   - `tests/e2e/test_valuation_pipeline.py`
4. Repository and integration behavior:
   - `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Original Acceptance Criteria Alignment

Original intent is satisfied:
1. Lifecycle fields exist and are used.
2. Scheduler avoids pre-open-date over-scheduling.
3. Missing-position path is terminal and does not pollute DLQ.
4. Unit/integration/e2e evidence exists for scheduler, consumer, and pipeline behavior.

## Rollout and Backward Compatibility

No breaking API contract changes are introduced by this refresh.
Current behavior is production-compatible with existing job and snapshot contracts.

## Open Questions

1. Should `SKIPPED_NO_POSITION` trend thresholds be explicitly added to operational runbooks as early drift signals?

## Next Actions

1. Keep RFC 003 classification as `Fully implemented and aligned`.
2. Monitor valuation job terminal-state distributions (`COMPLETE`, `FAILED`, `SKIPPED_NO_POSITION`) as part of routine operations quality checks.
