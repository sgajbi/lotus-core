# CR-474: Calculation Instrument Lookup Security Id Normalization

Date: 2026-05-28

## Scope

Instrument lookup query shape in cost, valuation, and timeseries calculation repositories.

## Finding

Cost, valuation, and timeseries repositories looked up instruments with raw `security_id` equality.
Padded caller values or historical padded instrument master rows could make an available instrument
look missing. That can block or degrade cost calculation, valuation currency discovery, position
timeseries enrichment, portfolio aggregation, and downstream analytics evidence.

For private banking calculation paths, instrument lookup should be deterministic and aligned with
the query-service read-plane posture, which trims security identifiers at lookup boundaries while
preserving case semantics.

## Change

Updated calculation repository lookups so:

1. cost-calculator `get_instrument(...)` trims caller and persisted instrument security IDs,
2. shared valuation `get_instrument(...)` trims caller and persisted instrument security IDs,
3. shared timeseries `get_instrument(...)` and `get_instruments_by_ids(...)` trim caller and
   persisted instrument security IDs,
4. batched timeseries lookup drops blank identifiers before querying.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
4. `python -m pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service -q`
5. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
6. `python -m ruff check src/services/calculators/cost_calculator_service/app/repository.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
7. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/repository.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py tests/unit/services/timeseries_generator_service/timeseries-generator-service/repositories/test_unit_timeseries_repo.py`
8. `git diff --check`

Results:

1. Focused calculation repository proof: `32 passed`
2. Cost-calculator unit pack: `106 passed`
3. Position valuation calculator unit pack: `34 passed`
4. Timeseries generator unit pack: `45 passed`
5. Portfolio-common unit pack: `486 passed`
6. Touched-surface ruff: passed
7. Touched-surface format check: passed
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Calculation repositories now use trim-normalized instrument lookup semantics for cost, valuation,
and timeseries generation.
