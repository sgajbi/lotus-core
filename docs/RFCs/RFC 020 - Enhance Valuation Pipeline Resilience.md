# RFC 020 - Enhance Valuation Pipeline Resilience

| Metadata | Value |
| --- | --- |
| Status | Outdated |
| Created | 2025-09-01 |
| Last Updated | 2026-03-04 |
| Owners | `position_valuation_calculator`, `portfolio-common` |
| Depends On | RFC 003, RFC 018 |
| Scope | Valuation consumer resiliency semantics and scheduler workload topology |

## Executive Summary

RFC 020 proposed two major changes:
1. Treat transient valuation data gaps as retriable pending jobs with delayed re-attempt policy.
2. Split `ValuationScheduler` into a separate `valuation-scheduler-service`.

Current system evolved along a different path:
1. Job lifecycle/observability hardening exists, but missing-position cases are explicitly terminally skipped (`SKIPPED_NO_POSITION`) rather than retried.
2. Scheduler remains in `position_valuation_calculator` service; workload isolation is handled with internal component separation and additional worker paths.

Because the design intent and current implementation diverged, this RFC is classified as `Outdated (requires revision)`.

## Original Requested Requirements (Preserved)

Original RFC 020 requested:
1. Data-gap resilience: keep jobs `PENDING` on transient missing data and retry with backoff.
2. Alert on repeated failed attempts via `attempt_count` thresholds.
3. Topology split: move scheduler logic into dedicated microservice.
4. Keep valuation consumer focused on low-latency compute path.

## Current Implementation Reality

Implemented in current codebase:
1. Durable job lifecycle fields exist (`attempt_count`, `failure_reason`) and are used in valuation job repository/update paths.
2. Scheduler claims jobs atomically and runs stale-reset recovery.
3. `ValuationConsumer` treats missing position history as `SKIPPED_NO_POSITION` terminal state, not PENDING retry.
4. Missing critical reference entities can mark job `FAILED`.
5. Scheduler remains in-process with valuation service (`consumer_manager` starts scheduler directly).

Evidence:
- `src/libs/portfolio-common/portfolio_common/database_models.py`
- `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
- `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`
- `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
- `src/services/calculators/position_valuation_calculator/app/consumer_manager.py`
- `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`
- `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Retry transient data-gap jobs as PENDING with backoff | Not implemented as specified; missing-position path is terminal skip (`SKIPPED_NO_POSITION`) | `valuation_consumer.py`; consumer tests |
| Attempt/failure metadata for operations | Implemented | `database_models.py`; `valuation_repository.py` |
| Dedicated scheduler microservice split | Not implemented; scheduler runs in same service process | `consumer_manager.py`; `valuation_scheduler.py` |
| Improve valuation operability/visibility | Implemented partially through job fields, status transitions, and metrics | repository + monitoring usage |

## Design Reasoning and Trade-offs

1. Terminal `SKIPPED_NO_POSITION` semantics avoid endless retries for dates where no position existed, reducing noise.
2. Keeping scheduler in-process simplifies deployment and local operations, at cost of weaker independent scaling control.
3. Existing claim/reset logic plus metrics provide practical resilience without introducing service boundary complexity.

Trade-off:
- The original RFC intent is no longer an accurate architecture record, which increases documentation drift risk.

## Gap Assessment

Primary gap is architectural/documentation drift, not immediate correctness breakage:
1. RFC text does not reflect current terminal-skip semantics.
2. RFC text describes a microservice split that was not adopted.
3. Potential future enhancement remains: explicit policy for when missing FX/price should trigger delayed retry versus terminal status.

## Deviations and Evolution Since Original RFC

1. RFC 003 and later reliability work operationalized valuation lifecycle and observability without the proposed service split.
2. RFC 018 introduced durable reprocessing job queue and worker, reducing urgency of splitting scheduler solely for fan-out reasons.

## Proposed Changes

1. Rebaseline RFC 020 as a current-state valuation resilience record.
2. Explicitly codify policy matrix for terminal vs retryable valuation failure modes (missing position, missing FX, missing instrument/portfolio, DB transient faults).
3. Keep microservice split as optional future architecture decision, not assumed baseline.

## Test and Validation Evidence

1. Consumer behavior for `DataNotFoundError` (skip/no DLQ):
   - `tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py`
2. Scheduler claim/reset behavior and metrics:
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
3. Schema-level support for lifecycle fields:
   - `portfolio_common/database_models.py`

## Original Acceptance Criteria Alignment

Partially aligned:
1. Lifecycle metadata/operability are present.
2. Proposed retry semantics and service split are not implemented as written.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. For missing FX/price on valuation date, should policy move to delayed retry under bounded attempts, or remain terminal with reprocessing-only recovery?
2. At what workload threshold does scheduler service extraction become justified versus in-process isolation?

## Next Actions

1. Track policy clarification and optional implementation under `RFC-020` deltas in `RFC-DELTA-BACKLOG.md`.
2. Keep current code behavior unchanged until policy decision is approved.
