# CR-481: Shared Lookup Identifier Normalization Helper

Date: 2026-05-28

## Scope

Identifier normalization helper duplication across calculation repositories.

## Finding

Cost, position, valuation, and shared timeseries repositories each carried local identifier-trimming
helpers after the normalized lookup hardening slices. The behavior was intentionally the same:
convert source identifiers to strings, trim boundary whitespace, preserve case semantics, and use
the result for tolerant read-boundary lookup predicates.

Keeping that policy duplicated across repositories makes later hardening riskier because one
calculator can drift from another. For banking-grade calculation paths, common lookup policy should
be explicit, reusable, and directly tested in `portfolio_common`.

## Change

Added `portfolio_common.identifiers.normalize_lookup_identifier(...)` and reused it in:

1. `CostCalculatorRepository`,
2. `PositionRepository`,
3. `TimeseriesRepositoryBase`,
4. `ValuationRepositoryBase`.

The helper preserves the existing semantics: trim whitespace, preserve case, return an empty lookup
key for `None`, and stringify non-string source identifiers before trimming.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_identifiers.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service tests/unit/services/calculators/position_calculator tests/unit/services/timeseries_generator_service/timeseries-generator-service tests/unit/services/calculators/position_valuation_calculator tests/unit/services/portfolio_aggregation_service -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/identifiers.py src/services/calculators/cost_calculator_service/app/repository.py src/services/calculators/position_calculator/app/repositories/position_repository.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_identifiers.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/identifiers.py src/services/calculators/cost_calculator_service/app/repository.py src/services/calculators/position_calculator/app/repositories/position_repository.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_identifiers.py`
6. `git diff --check`

Results:

1. Focused shared identifier/repository proof: `49 passed`
2. Affected calculator and aggregation packs: `276 passed`
3. Portfolio-common unit pack: `490 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Calculation lookup identifier normalization is now centralized and directly tested.
