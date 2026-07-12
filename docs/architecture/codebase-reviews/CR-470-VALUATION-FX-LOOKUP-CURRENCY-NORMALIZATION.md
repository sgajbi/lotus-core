# CR-470: Valuation FX Lookup Currency Normalization

Date: 2026-05-28

## Scope

Shared valuation repository FX-rate lookup query shape for cross-currency position valuation.

## Finding

`ValuationRepositoryBase.get_fx_rate(...)` normalized caller currencies but still compared against
raw persisted `fx_rates.from_currency` and `fx_rates.to_currency` values. Historical lower-case or
padded FX rows could therefore be missed by valuation workers even though the platform owns a
normalized functional FX lookup index.

For private banking portfolio valuation, FX lookup must be deterministic and should not depend on
historical source formatting. Missing an available rate can set cross-currency value to zero,
produce false data-quality warnings, and distort downstream allocation, performance, risk, and
reporting evidence.

## Change

Updated the shared valuation repository so:

1. caller currencies use the shared `portfolio_common.currency_codes.normalize_currency_code(...)`
   helper,
2. persisted FX rows are compared through `upper(trim(...))` predicates that match the existing
   `ix_fx_rates_normalized_pair_rate_date` functional index,
3. repository tests prove padded lower-case input compiles to normalized predicates while
   preserving the as-of date fence and latest-rate ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
6. `git diff --check`

Results:

1. Focused valuation repository proof: `7 passed`
2. Position valuation calculator unit pack: `31 passed`
3. Portfolio-common unit pack: `486 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Shared
valuation workers now use normalized, functional-index-compatible FX lookup semantics for
cross-currency portfolio valuation.
