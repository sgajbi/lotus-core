# CR-472: Timeseries FX Lookup Currency Normalization

Date: 2026-05-28

## Scope

Shared timeseries repository FX-rate lookup used by position and portfolio timeseries generation.

## Finding

`TimeseriesRepositoryBase.get_fx_rate(...)` compared raw caller currency values directly against
persisted FX rows. Padded/lower-case caller values or historical non-canonical FX rows could make
an available rate look missing during portfolio aggregation and position timeseries generation.

For private banking analytics, timeseries generation is an authoritative downstream calculation
path. It should use the same normalized reference-data semantics as valuation, cost, reconciliation,
and query-service lookup paths.

## Change

Updated the shared timeseries repository so:

1. caller currencies use the shared `portfolio_common.currency_codes.normalize_currency_code(...)`
   helper,
2. persisted FX rows are compared through `upper(trim(...))` predicates compatible with the
   existing `ix_fx_rates_normalized_pair_rate_date` functional index,
3. repository tests prove padded lower-case input compiles to normalized predicates while
   preserving the as-of date fence and latest-rate ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py -q`
2. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
6. `git diff --check`

Results:

1. Focused timeseries repository proof: `17 passed`
2. Timeseries generator unit pack: `43 passed`
3. Portfolio-common unit pack: `486 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Shared
timeseries generation now uses normalized, functional-index-compatible FX lookup semantics for
cross-currency position and portfolio timeseries calculations.
