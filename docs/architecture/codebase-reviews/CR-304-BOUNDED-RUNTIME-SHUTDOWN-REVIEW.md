# CR-304 Bounded Runtime Shutdown Review

## Summary

`shutdown_runtime_components(...)` claimed to guarantee bounded shutdown, but it simply awaited:

- `asyncio.gather(*tasks, return_exceptions=True)`

If any managed task ignored its stop signal or got stuck, service shutdown could hang forever.

## Why This Matters

This helper is shared across many worker services. If its shutdown contract is unbounded, one
stuck task can hang teardown for the whole service even when the rest of the runtime is already
stopping correctly.

## Change

- added `shutdown_timeout_seconds` to `shutdown_runtime_components(...)`
- wrapped the final gather in `asyncio.wait_for(...)`
- on timeout:
  - cancel remaining tasks
  - gather again with `return_exceptions=True`

## Evidence

- added direct unit proof in:
  - `tests/unit/libs/portfolio-common/test_runtime_supervision.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_runtime_supervision.py -q`
    - `4 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/runtime_supervision.py tests/unit/libs/portfolio-common/test_runtime_supervision.py`
    - passed

## Follow-up

- if we want richer operator evidence later, the next step would be logging which tasks required
  forced cancellation after timeout. The core bounded-shutdown guarantee is now in place.
