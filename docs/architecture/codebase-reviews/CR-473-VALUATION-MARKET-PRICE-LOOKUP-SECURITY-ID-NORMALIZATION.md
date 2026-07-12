# CR-473: Valuation Market Price Lookup Security Id Normalization

Date: 2026-05-28

## Scope

Shared valuation repository market-price lookup query shape for latest price and next price date.

## Finding

`ValuationRepositoryBase.get_latest_price_for_position(...)` and `get_next_price_date(...)`
compared raw `security_id` values directly against persisted market-price rows. Padded caller
values or historical padded market-price rows could make an available price look missing, blocking
or distorting valuation and revaluation scheduling.

For private banking valuation, market-price lookup should be deterministic and aligned with the
read-plane price repository posture, which already trims market-price security identifiers.

## Change

Updated the shared valuation repository so:

1. caller security identifiers are normalized by trimming whitespace,
2. persisted market-price rows are compared through `trim(market_prices.security_id)`,
3. repository tests prove latest-price and next-price-date queries trim caller and persisted
   identifiers while preserving date fences and ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m pytest tests/unit/services/calculators/position_valuation_calculator -q`
3. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py`
6. `git diff --check`

Results:

1. Focused valuation repository proof: `9 passed`
2. Position valuation calculator unit pack: `33 passed`
3. Portfolio-common unit pack: `486 passed`
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Shared
valuation workers now use trim-normalized market-price lookup semantics for latest price discovery
and revaluation scheduling.
