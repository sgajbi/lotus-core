# CR-1008: Runtime Supervision Teardown Boundary

Date: 2026-06-05

## Scope

Split shared runtime teardown into focused consumer shutdown, stop-callback execution, server exit
signaling, task awaiting, timeout logging, timed-out task naming, and forced-cancellation helpers
without changing shutdown ordering, callback failure continuation, server `should_exit` signaling,
bounded task waiting, timeout task attribution, or final `return_exceptions=True` gather behavior.

## Finding

`shutdown_runtime_components` mixed consumer shutdown discovery, consumer failure logging, stop
callback execution, stop callback failure logging, embedded-server exit signaling, empty-task
handling, bounded task awaiting, timeout task-name extraction, timeout logging, task cancellation,
and final gather cleanup in one C-ranked helper. That made the common service teardown path harder
to audit as more Lotus services reuse the shared runtime supervision helper.

## Action

Added focused helpers for consumer shutdown, stop-callback execution, server exit signaling,
runtime-task awaiting, timeout handling, timed-out task-name extraction, pending-task cancellation,
and teardown error logging. The public `shutdown_runtime_components` function remains the ordered
orchestration boundary.

## Result

`shutdown_runtime_components` improved from `C (18)` to `A (1)`. Every function in
`runtime_supervision.py` now reports A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (51.77)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_runtime_supervision.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\runtime_supervision.py tests\unit\libs\portfolio-common\test_runtime_supervision.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\runtime_supervision.py tests\unit\libs\portfolio-common\test_runtime_supervision.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\runtime_supervision.py -s`
  => `shutdown_runtime_components` `A (1)` and every function in the module A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\runtime_supervision.py -s`
  => `runtime_supervision.py` `A (51.77)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\runtime_supervision.py`
  => 141 SLOC / 101 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared runtime-supervision helper refactor
that preserves existing service teardown semantics.
