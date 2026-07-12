# CR-1020: Reprocessing Job Stale Reset Boundary

Date: 2026-06-05

## Scope

Reduce shared reprocessing stale-job reset complexity while preserving stale cutoff calculation,
stale processing-row selection, max-attempt failure behavior, retryable reset behavior,
processing-state rechecks, stale cutoff rechecks, warning logs, and reset rowcount reporting.

## Finding

`ReprocessingJobRepository.find_and_reset_stale_jobs` mixed stale cutoff calculation, stale-row
query construction, database execution, stale-row classification, failed update construction,
failed update execution, warning logging, retryable update construction, retryable update
execution, and return-count behavior in one B-ranked method.

## Action

Added focused helpers for stale-row retrieval, over-limit stale-job classification, retryable
stale-job classification, failed update construction, reset update construction, shared
processing-state update predicates, failed-job marking, and retryable-job reset.

## Result

`ReprocessingJobRepository.find_and_reset_stale_jobs` improved from `B (8)` to `A (2)`. Every
function/class/method in `reprocessing_job_repository.py` now reports A-ranked cyclomatic
complexity, and the module remains A-ranked maintainability at `A (42.85)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_reprocessing_job_repository.py -q`
  => 18 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\reprocessing_job_repository.py tests\unit\libs\portfolio-common\test_reprocessing_job_repository.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\reprocessing_job_repository.py tests\unit\libs\portfolio-common\test_reprocessing_job_repository.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\libs\portfolio-common\portfolio_common\reprocessing_job_repository.py -s`
  => `ReprocessingJobRepository.find_and_reset_stale_jobs` `A (2)` and every function/class/method
  A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\reprocessing_job_repository.py -s`
  => `reprocessing_job_repository.py` `A (42.85)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\reprocessing_job_repository.py`
  => 329 SLOC / 116 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared reprocessing repository refactor
that preserves existing stale-job reset semantics.
