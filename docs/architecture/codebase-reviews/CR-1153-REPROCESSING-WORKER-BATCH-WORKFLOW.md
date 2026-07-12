# CR-1153 Reprocessing Worker Batch Workflow

Date: 2026-06-22

## Scope

Durable valuation reprocessing worker batch processing in
`src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`.

## Finding

`ReprocessingWorker._process_batch(...)` mixed database session setup, repository construction,
stale job reset, queue metric updates, job claiming, claimed metric observation, per-job correlation
context, job payload parsing, impacted portfolio lookup, later-holding fallback lookup, watermark
fanout, stale ownership skip logging, no-op requeue posture, terminal status updates, completion
metrics, failure marking, failure metrics, and correlation reset in one C-ranked worker method.

Radon reported:

- `_process_batch`: `C (18)`

## Action Taken

Extracted focused helpers for:

- reset-watermark job scope parsing,
- watermark fanout observation/logging,
- stale reset and job claiming,
- per-job correlation-scoped processing,
- impacted portfolio lookup with later-holding fallback,
- watermark reset/no-op decisioning,
- terminal status update and ownership-loss posture,
- failed job marking.

The transaction/session boundary, durable job type, stale reset settings, queue metric updates,
claim metrics, correlation propagation, no-op requeue behavior, completion metrics, failure metrics,
and job status transitions remain unchanged.

## Evidence

Focused unit proof:

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_reprocessing_worker.py -q`
- Result: `12 passed`

Focused static proof:

- `python -m ruff check src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py -s --exclude "*/build/*"`
- Result: `_process_batch` is `A (3)`

Measured movement:

- `_process_batch`: `C (18)` -> `A (3)`
- `reprocessing_worker.py`: no C-or-worse functions/classes remain

## Residual Risk

This slice does not change durable job repository contracts, valuation repository lookup semantics,
watermark update semantics, or worker polling behavior. Remaining C-ranked hotspots are in
`valuation_scheduler.py`.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of durable reprocessing job handling,
- separation of ownership-loss and no-op requeue postures,
- direct proof across success, partial stale skips, failures, stale reset, settings, and queue
  metric paths.

It does not claim full bank-buyable readiness for `lotus-core`.
