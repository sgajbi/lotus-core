# CR-311 Runtime Failure Attribution Ordering Review

## Summary

`wait_for_shutdown_or_task_failure(...)` selected `next(iter(done))` when multiple runtime tasks
completed together. If a real task failure and an unrelated cancellation or clean exit happened in
the same wait result, the helper could attribute shutdown to the wrong task.

## Why This Matters

This helper is shared across worker services. Runtime failure attribution needs to be deterministic
and preserve the real cause, otherwise incident evidence becomes noisy exactly when a service is
already unstable.

## Change

- changed completed-task selection order to prefer:
  - real exception-bearing failures
  - then cancelled tasks
  - then clean exits

## Evidence

- added direct unit proof in:
  - `tests/unit/libs/portfolio-common/test_runtime_supervision.py`
- validation:
  - `python -m pytest tests/unit/libs/portfolio-common/test_runtime_supervision.py -q`
    - `7 passed`
  - `python -m ruff check src/libs/portfolio-common/portfolio_common/runtime_supervision.py tests/unit/libs/portfolio-common/test_runtime_supervision.py`
    - passed

## Follow-up

- no immediate follow-up needed here. The key correction is deterministic attribution of the real
  failing task when multiple tasks complete at once.
