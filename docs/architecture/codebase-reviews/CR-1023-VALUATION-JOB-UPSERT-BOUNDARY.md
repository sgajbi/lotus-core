# CR-1023: Valuation Job Upsert Boundary

Date: 2026-06-05

## Scope

Reduce shared valuation job upsert complexity while preserving deduplication, stale epoch
filtering, conflict update semantics, processing-job non-rearm behavior, same-correlation
pending/complete non-rearm behavior, staged-count reporting, superseded pending job marking, debug
logging, and error logging/propagation.

## Finding

`ValuationJobRepository.upsert_jobs` mixed normalization, latest epoch lookup, stale-job filtering,
insert value construction, PostgreSQL conflict update construction, conflict predicate
construction, returning-column execution, staged-count materialization, superseded pending job
marking, debug logging, and exception logging in one B-ranked method.

## Action

Added focused helpers for eligible job filtering, upsert execution, insert value construction,
conflict update values, conflict update predicates, and staged upsert logging while preserving the
existing public repository behavior and SQL conflict policy.

## Result

`ValuationJobRepository.upsert_jobs` improved from `B (7)` to `A (4)`. Every function/class/method
in `valuation_job_repository.py` now reports A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (47.61)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_valuation_job_repository.py -q`
  => 6 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_job_repository.py tests\unit\libs\portfolio-common\test_valuation_job_repository.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\valuation_job_repository.py tests\unit\libs\portfolio-common\test_valuation_job_repository.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\libs\portfolio-common\portfolio_common\valuation_job_repository.py -s`
  => `ValuationJobRepository.upsert_jobs` `A (4)` and every function/class/method A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\valuation_job_repository.py -s`
  => `valuation_job_repository.py` `A (47.61)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\valuation_job_repository.py`
  => 262 SLOC / 101 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared valuation job repository refactor
that preserves existing job staging and conflict-update semantics.
