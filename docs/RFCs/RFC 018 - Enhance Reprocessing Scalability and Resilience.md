# RFC 018 - Enhance Reprocessing Scalability and Resilience

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2025-09-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core calculators (`position_calculator`, `position_valuation_calculator`), `portfolio-common` |
| Depends On | RFC 001, RFC 004 |
| Scope | Durable fan-out for instrument reprocessing triggers and atomic replay trigger flow |

## Executive Summary

RFC 018 addressed two high-risk operational concerns in the reprocessing path:
1. Fan-out spikes from back-dated instrument prices (thundering herd risk).
2. Non-atomic epoch bump + replay publication in position replay flow.

Current lotus-core implementation aligns with both goals:
1. Instrument-level triggers are converted into durable jobs (`reprocessing_jobs`) and processed by a bounded worker.
2. Position replay trigger uses outbox-backed atomic staging so epoch bump and replay publication intent commit together.

## Original Requested Requirements (Preserved)

Original RFC 018 requested:
1. Replace in-memory instrument trigger fan-out with durable queue-backed jobs.
2. Add controlled worker processing for watermark reset jobs.
3. Add observable pending-trigger metric.
4. Make position replay trigger atomic by staging replay events durably in the same transaction as epoch bump.

## Current Implementation Reality

Implemented behavior:
1. Durable queue introduced: `reprocessing_jobs` table and repository claim/update workflow.
2. `ValuationScheduler` converts instrument triggers into `RESET_WATERMARKS` jobs.
3. `ReprocessingWorker` claims jobs in batches and applies watermark resets across affected portfolios.
4. `instrument_reprocessing_triggers_pending` gauge is emitted from scheduler metric update path.
5. `PositionCalculator` uses outbox-backed replay staging after epoch increment in a single transaction scope.

Evidence:
- `alembic/versions/2e3ca6475106_feat_add_reprocessing_jobs_table.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py`
- `src/services/calculators/position_valuation_calculator/app/core/reprocessing_worker.py`
- `src/services/calculators/position_calculator/app/core/position_logic.py`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
- `tests/unit/services/calculators/position_valuation_calculator/core/test_reprocessing_worker.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Durable queue for trigger fan-out | `reprocessing_jobs` schema + repository + worker claim loop | alembic migration; `reprocessing_job_repository.py`; worker tests |
| Controlled fan-out processing | `ReprocessingWorker` bounded polling/batching and status transitions | `reprocessing_worker.py`; worker unit tests |
| Pending-trigger observability | Gauge `instrument_reprocessing_triggers_pending` set by scheduler | `monitoring.py`; `valuation_scheduler.py` |
| Atomic replay trigger | Epoch bump + replay event staging via outbox inside transaction scope | `position_logic.py`; position logic tests |

## Design Reasoning and Trade-offs

1. Durable DB jobs were chosen over in-memory fan-out to prioritize recoverability and bounded load.
2. Worker/scheduler split inside the same service avoided introducing cross-service network complexity while still decoupling control-plane workloads.
3. Outbox atomicity reduces recovery burden by making replay intent durable before any asynchronous publish.

Trade-off:
- Additional table/worker complexity and operational monitoring overhead are accepted for reliability.

## Gap Assessment

No material implementation gap remains against RFC 018 intent.

## Deviations and Evolution Since Original RFC

1. Implementation is documented and reinforced further in architecture notes (`adr_002_reprocessing_scalability.md`) and follow-on reliability hardening (RFC 065).
2. Queue claim path later received index/perf improvements (`b0c1d2e3f4a5...`) for higher load scenarios.

## Proposed Changes

1. Keep RFC 018 classification as `Fully implemented and aligned`.
2. Continue load validation via RFC 065/066 reliability packs.

## Test and Validation Evidence

1. Scheduler trigger-to-job conversion tests:
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_valuation_scheduler.py`
2. Reprocessing worker claim/process/failure tests:
   - `tests/unit/services/calculators/position_valuation_calculator/core/test_reprocessing_worker.py`
3. Repository atomic claim SQL checks:
   - `tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py`
4. Atomic replay orchestration checks in position logic:
   - `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`

## Original Acceptance Criteria Alignment

All key acceptance goals are met:
1. Durable trigger queue exists.
2. Controlled worker processing exists.
3. Pending queue metric exists.
4. Atomic replay trigger path implemented via outbox pattern.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should reprocessing job retention/TTL policy be formalized in a separate ops RFC for long-term table growth control?

## Next Actions

1. Keep as implemented baseline.
2. Track only operational scaling refinements under RFC 065/066.
