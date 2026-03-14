# CR-298 Worker And Scheduler Shutdown Interrupt Review

## Summary

`ReprocessingWorker`, `ValuationScheduler`, and `AggregationScheduler` only flipped
their local `_running` flags during shutdown. If the runtime asked them to stop while
they were sleeping between polls, shutdown could stall for the full poll interval even
though no more useful work remained.

## Why This Matters

These loops run inside the shared worker runtime shutdown contract. A stop callback that
waits for the next `sleep(...)` timeout is not a graceful shutdown signal in practice;
it is a delayed shutdown request. That stretches service teardown by 5 to 60 seconds
depending on configuration and makes lifecycle behavior look cleaner than it really is.

## Change

- Added `_stop_event` to:
  - `ReprocessingWorker`
  - `ValuationScheduler`
  - `AggregationScheduler`
- `stop()` now:
  - flips `_running = False`
  - sets `_stop_event`
- poll loops now wait on:
  - `await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)`
- shutdown now exits immediately after the current poll work completes instead of
  waiting for the next poll timeout boundary.

## Evidence

- Added direct unit proofs that stop interrupts long poll sleeps:
  - `tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py`
  - `tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py`
  - `tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`
- Validation:
  - `python -m pytest tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py -q`
    - `32 passed`
  - `python -m ruff check src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py tests/unit/services/portfolio_aggregation_service/core/test_aggregation_scheduler.py`
    - passed

## Follow-up

- Review any remaining long-poll runtime component that still treats shutdown as
  `set flag -> wait for next timeout`, especially outside these three core loops.
