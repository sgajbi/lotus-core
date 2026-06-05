# CR-1007: Runtime Supervision Failure Attribution Boundary

Date: 2026-06-05

## Scope

Split shared runtime supervision failure attribution into focused completed-task selection,
exception-task selection, cancelled-task selection, and runtime-error construction helpers without
changing explicit shutdown behavior, failure-over-cancellation ordering, cancelled-task
classification, clean-exit classification, exception cause preservation, shutdown-event signaling,
or shutdown-wait task cleanup.

## Finding

`wait_for_shutdown_or_task_failure` mixed shutdown wait orchestration, completed-task filtering,
failure-priority selection, cancelled-task fallback, clean-exit fallback, runtime-error message
construction, exception cause assignment, shutdown signaling, and cleanup in one C-ranked helper.
That made the shared service-supervision contract harder to audit as more consumer managers reused
the helper.

## Action

Added focused helpers for selecting the failed runtime task, finding exception-bearing tasks,
finding cancelled tasks, and constructing the returned `RuntimeError`. Existing tests continue to
prove explicit shutdown, failed-task reporting, failure-over-cancellation ordering, shutdown
signaling, and exception cause preservation.

## Result

`wait_for_shutdown_or_task_failure` improved from `C (15)` to `A (5)`. The extracted failure
attribution helpers are A-ranked, and `runtime_supervision.py` remains A-ranked maintainability at
`A (56.39)`. `shutdown_runtime_components` remains a separate C-ranked teardown hotspot for a later
slice.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_runtime_supervision.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\runtime_supervision.py tests\unit\libs\portfolio-common\test_runtime_supervision.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\runtime_supervision.py tests\unit\libs\portfolio-common\test_runtime_supervision.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\runtime_supervision.py -s`
  => `wait_for_shutdown_or_task_failure` `A (5)`, `_select_failed_runtime_task` `A (3)`,
  `_find_exception_runtime_task` `A (4)`, `_find_cancelled_runtime_task` `A (3)`, and
  `_runtime_error_for_failed_task` `A (4)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\runtime_supervision.py -s`
  => `runtime_supervision.py` `A (56.39)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\runtime_supervision.py`
  => 108 SLOC / 76 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared runtime-supervision helper refactor
that preserves existing service shutdown/failure attribution semantics.
