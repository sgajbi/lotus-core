# CR-1024: Timeseries Stale Job Reset Boundary

Date: 2026-06-05

## Scope

Reduce shared timeseries stale aggregation job reset complexity while preserving stale-row
discovery, max-attempt failure marking, retryable reset behavior, processing-state rechecks,
stale-age rechecks, warning logs, and return-count semantics.

## Finding

`TimeseriesRepositoryBase.find_and_reset_stale_jobs` mixed stale threshold calculation, stale-row
query construction, database execution, stale-row classification, failed update
construction/execution, warning logging, retryable update construction/execution, and return-count
behavior in one B-ranked method.

## Action

Added focused helpers for stale aggregation job retrieval, over-limit and retryable stale-job
classification, failed update construction, reset update construction, shared processing-state
update predicates, failed-job marking, and retryable-job reset while preserving the existing public
repository behavior and SQL update predicates.

## Result

`TimeseriesRepositoryBase.find_and_reset_stale_jobs` improved from `B (9)` to `A (2)`. Every stale
aggregation job reset helper reports A-ranked cyclomatic complexity, and
`timeseries_repository_base.py` remains A-ranked maintainability at `A (19.49)`.

## Evidence

- `python -m pytest tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py -q`
  => 30 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py`
  => 1 file reformatted, 2 files left unchanged
- `python -m radon cc src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py -s`
  => `TimeseriesRepositoryBase.find_and_reset_stale_jobs` `A (2)` and every stale reset helper A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py -s`
  => `timeseries_repository_base.py` `A (19.49)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py`
  => 598 SLOC / 212 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared timeseries repository refactor that
preserves existing stale aggregation job reset and failure semantics.
