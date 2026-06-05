# CR-1025: Timeseries Upsert Boundary

Date: 2026-06-05

## Scope

Reduce shared position and portfolio timeseries upsert complexity while preserving inserted-column
selection, timestamp-audit exclusion, PostgreSQL conflict key selection, conflict update values,
database execution, info logging, and exception logging/propagation.

## Finding

`TimeseriesRepositoryBase.upsert_position_timeseries` and
`TimeseriesRepositoryBase.upsert_portfolio_timeseries` duplicated inline insert-value extraction,
conflict-update value construction, PostgreSQL upsert statement assembly, database execution,
success logging, and exception logging in two B-ranked repository methods.

## Action

Added focused helpers for position and portfolio timeseries upsert statement construction, shared
insert-value extraction, shared conflict-update value construction, and shared PostgreSQL
conflict-update assembly. The public repository methods remain the async execution and logging
boundary.

## Result

`TimeseriesRepositoryBase.upsert_position_timeseries` improved from `B (6)` to `A (2)`, and
`TimeseriesRepositoryBase.upsert_portfolio_timeseries` improved from `B (6)` to `A (2)`. Every
function/class/method in `timeseries_repository_base.py` now reports A-ranked cyclomatic
complexity, and the module remains A-ranked maintainability at `A (19.94)`.

## Evidence

- `python -m pytest tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py -q`
  => 30 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py tests\unit\services\timeseries_generator_service\timeseries-generator-service\repositories\test_unit_timeseries_repo.py tests\unit\services\portfolio_aggregation_service\repositories\test_timeseries_repository.py`
  => 1 file reformatted, 2 files left unchanged
- `python -m radon cc src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py -s`
  => both upsert methods `A (2)` and every function/class/method A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py -s`
  => `timeseries_repository_base.py` `A (19.94)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\timeseries_repository_base.py`
  => 608 SLOC / 216 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared timeseries repository refactor that
preserves existing position and portfolio timeseries upsert semantics.
