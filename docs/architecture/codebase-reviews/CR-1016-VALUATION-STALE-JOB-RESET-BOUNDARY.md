# CR-1016: Valuation Stale Job Reset Boundary

Date: 2026-06-05

## Scope

Split shared valuation stale-job reset orchestration into focused stale-row lookup, stale-row
classification, superseded-job marking, over-limit failure marking, retryable-job reset, and update
statement builders without changing stale threshold calculation, processing-state rechecks,
superseded handling, max-attempt failure behavior, reset metrics, or reset count reporting.

## Finding

`ValuationRepositoryBase.find_and_reset_stale_jobs` mixed stale threshold calculation, newer-epoch
lookup, stale row fetching, superseded/failed/reset classification, three update statement
families, logging, reset metrics, and return-count behavior in one C-ranked method. This is shared
worker infrastructure used by valuation and reprocessing schedulers.

## Action

Added focused helpers for stale-row retrieval, stale-row grouping, stale-job ID classification,
superseded update construction, failed update construction, reset update construction, and shared
processing-state update predicates. Existing direct tests continue to prove reset metric emission,
max-attempt failure behavior, superseded-row skipping, and processing-state rechecks.

## Result

`ValuationRepositoryBase.find_and_reset_stale_jobs` improved from `C (14)` to `A (2)`. All stale
job reset helper functions now report A-ranked cyclomatic complexity, and
`valuation_repository_base.py` remains B-ranked maintainability at `B (13.79)`.

## Evidence

- `python -m pytest tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py -q`
  => 18 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_repository_base.py tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\valuation_repository_base.py tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\valuation_repository_base.py -s`
  => `ValuationRepositoryBase.find_and_reset_stale_jobs` `A (2)` and all stale reset helpers
  A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\valuation_repository_base.py -s`
  => `valuation_repository_base.py` `B (13.79)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\valuation_repository_base.py`
  => 808 SLOC / 287 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared valuation repository refactor that
preserves existing stale-job reset semantics.
