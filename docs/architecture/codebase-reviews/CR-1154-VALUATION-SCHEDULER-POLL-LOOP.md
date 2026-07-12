# CR-1154 Valuation Scheduler Poll Loop

Date: 2026-06-22

## Scope

- `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`

## Finding

`ValuationScheduler.run(...)` mixed scheduler lifecycle state, repeated database transaction setup,
reprocessing metric refresh, queue metric refresh, instrument-level trigger processing, stale
valuation job reset, backfill job creation, ready-job dispatch, watermark advancement, exception
handling, poll waiting, timeout continuation, and cancellation stop posture in one C-ranked runtime
loop.

This made the polling order harder to inspect and increased the risk of accidental behavior drift
when maintaining scheduler cadence, reset, dispatch, or watermark behavior.

## Action

Extracted focused helpers for:

- database poll-step transaction execution,
- combined reprocessing and queue metric refresh,
- stale valuation job reset,
- one complete scheduler poll iteration,
- stop-aware poll waiting.

The polling order, transaction boundaries, exception handling, stop-event behavior, and cancellation
posture are preserved.

## Measured Signal

- Before: `ValuationScheduler.run(...)` was `C (11)`.
- After: `ValuationScheduler.run(...)` is `A (4)`.
- Remaining C-ranked scheduler routines are explicit domain hotspots:
  - `ValuationScheduler._advance_watermarks(...)`: `C (18)`.
  - `ValuationScheduler._create_backfill_jobs(...)`: `C (20)`.

## Validation

- `python -m pytest tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py -q`
  - `20 passed`
- `python -m ruff check src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - passed
- `python -m ruff format src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
  - passed
- `python -m radon cc src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py -s --exclude "*/build/*"`
  - `ValuationScheduler.run - A (4)`

## Residual Risk

`_advance_watermarks(...)` and `_create_backfill_jobs(...)` remain C-ranked because they own
distinct valuation-domain workflows. They should be reduced in separate slices with focused
scheduler tests and measured evidence.

