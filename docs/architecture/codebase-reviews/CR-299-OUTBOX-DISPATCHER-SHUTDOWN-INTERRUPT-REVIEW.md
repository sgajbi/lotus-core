# CR-299 Outbox Dispatcher Shutdown Interrupt Review

## Summary

`OutboxDispatcher` only flipped `_running = False` during shutdown and then waited for the
next poll sleep to expire. If stop arrived just after a batch finished, service teardown
could stall for the full poll interval even though no more outbox work remained.

## Why This Matters

The dispatcher is part of the shared worker runtime for multiple services. Delayed stop
behavior stretches shutdown without adding safety and makes the runtime look more graceful
than it really is.

## Change

- Added `_stop_event` to `OutboxDispatcher`
- `stop()` now:
  - flips `_running = False`
  - sets `_stop_event`
- replaced bare `asyncio.sleep(...)` in `run()` with an interruptible stop wait:
  - `await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)`

## Evidence

- Added direct unit proof:
  - `tests/unit/libs/portfolio-common/test_outbox_dispatcher.py`
- Validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q`
    - `5 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py`
    - passed

## Follow-up

- Keep checking long-poll runtime helpers for the same delayed-stop pattern, especially
  shared infrastructure components used by multiple services.
