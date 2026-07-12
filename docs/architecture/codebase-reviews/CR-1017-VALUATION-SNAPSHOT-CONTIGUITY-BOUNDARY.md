# CR-1017: Valuation Snapshot Contiguity Boundary

Date: 2026-06-05

## Scope

Split shared valuation snapshot-contiguity SQL construction out of
`ValuationRepositoryBase.find_contiguous_snapshot_dates` into a dedicated shared module while
preserving first-open-date handling, business-date series generation, snapshot/history quantity
matching, first-gap detection, latest-snapshot fallback, and result-key materialization.

## Finding

`ValuationRepositoryBase.find_contiguous_snapshot_dates` mixed repository execution with optional
first-open-date values-table construction, date-series correlation, latest position-history lookup,
snapshot reconciliation predicates, gap detection, latest snapshot fallback, optional join
construction, and result mapping. The method was the remaining B-ranked method in
`valuation_repository_base.py` after CR-1016 and made a shared valuation repository harder to
review.

## Action

Added `valuation_snapshot_contiguity.py` as a focused shared query-builder module. The repository
method now only handles the empty-state guard, delegates statement construction to
`build_contiguous_snapshot_dates_stmt`, executes through the repository session, and delegates row
mapping to `contiguous_snapshot_dates_by_key`.

## Result

`ValuationRepositoryBase.find_contiguous_snapshot_dates` improved from `B (8)` to `A (3)`, leaving
every function/class/method in `valuation_repository_base.py` A-ranked by cyclomatic complexity.
The new `valuation_snapshot_contiguity.py` module is A-ranked by complexity and maintainability
at `A (41.06)`. `valuation_repository_base.py` improved from `B (13.79)` maintainability after
CR-1016 to `B (16.41)` and reduced from 808 SLOC / 287 LLOC to 676 SLOC / 263 LLOC.

## Evidence

- `python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_repository_base.py src\libs\portfolio-common\portfolio_common\valuation_snapshot_contiguity.py`
  => all checks passed
- `python -m pytest tests\unit\services\calculators\position_valuation_calculator\repositories\test_valuation_repository_worker_metrics.py -q`
  => 18 passed
- `python -m radon cc src\libs\portfolio-common\portfolio_common\valuation_repository_base.py src\libs\portfolio-common\portfolio_common\valuation_snapshot_contiguity.py -s`
  => `ValuationRepositoryBase.find_contiguous_snapshot_dates` `A (3)` and both modules fully
  A-ranked by cyclomatic complexity
- `python -m radon mi src\libs\portfolio-common\portfolio_common\valuation_repository_base.py src\libs\portfolio-common\portfolio_common\valuation_snapshot_contiguity.py -s`
  => `valuation_repository_base.py` `B (16.41)` and `valuation_snapshot_contiguity.py` `A (41.06)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\valuation_repository_base.py src\libs\portfolio-common\portfolio_common\valuation_snapshot_contiguity.py`
  => `valuation_repository_base.py` 676 SLOC / 263 LLOC and
  `valuation_snapshot_contiguity.py` 208 SLOC / 59 LLOC
- PostgreSQL dialect compilation of `build_contiguous_snapshot_dates_stmt` passed with and without
  first-open-date rows; the no-first-open-date variant confirmed the optional values join is not
  introduced.
- Docker-backed focused integration tests were attempted for the three existing contiguous
  snapshot scenarios, but local setup failed before application code because Docker Desktop was not
  running: `Docker engine is not available. Start Docker Desktop/daemon before running integration
  or E2E tests.`

## Wiki Decision

No wiki source update is required. This is an internal shared valuation repository/query-builder
refactor that preserves existing snapshot-contiguity semantics.
