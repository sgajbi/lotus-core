# CR-477: Timeseries Lookup Identifier Normalization

Date: 2026-05-28

## Scope

Shared timeseries repository lookup query shape for portfolio, snapshot, cashflow, position
timeseries, and portfolio timeseries reads.

## Finding

The shared timeseries repository still used raw portfolio/security equality for several calculation
reads after FX and instrument lookup hardening. Padded caller values or historical padded rows could
create false missing snapshots, split a single security across duplicate partitions, miss cashflows,
or load the wrong prior portfolio timeseries point.

Those failures can distort generated position timeseries, portfolio aggregation, performance
inputs, risk inputs, and downstream front-office analytics evidence. Identifier normalization must
therefore be applied consistently at the repository read boundary while preserving stored source
values and case semantics.

## Change

Updated `TimeseriesRepositoryBase` so:

1. repository-local identifier trimming is centralized through `_normalize_identifier(...)`,
2. portfolio, current-epoch, and all-snapshots reads trim portfolio IDs,
3. position-timeseries aggregation reads trim portfolio IDs and partition/join by trimmed security
   IDs,
4. snapshot lookback, future-snapshot, and latest-snapshot reads trim portfolio/security IDs and
   partition by trimmed security IDs where needed,
5. cashflow reads trim portfolio/security IDs before exact-date and date-list filtering,
6. portfolio-timeseries lookback trims portfolio IDs,
7. existing instrument lookup helpers reuse the same repository-local identifier normalization.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py -q`
2. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
6. `git diff --check`

Results:

1. Focused timeseries repository proof: `21 passed`
2. Timeseries generator unit pack: `47 passed`
3. Portfolio-common unit pack: `486 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Timeseries snapshot, cashflow, and aggregation reads now use trim-normalized identifier lookup
semantics at the repository boundary.
