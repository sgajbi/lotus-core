# CR-483: Non-Positive Market Price Valuation Guard

Date: 2026-05-28

## Scope

Read-side market-price positivity handling in the position valuation calculator.

## Finding

Authoritative market-price ingestion and shared market-price event models reject non-positive prices,
but `ValuationLogic` still trusted the price row it received from storage. A historical repair
mistake, manual database edit, or dirty legacy row with a zero or negative market price could
therefore produce zero or inverted market values and unrealized P&L.

For private-banking valuation, non-positive market prices must fail closed at the calculation
boundary even when upstream write boundaries are already hardened.

## Change

Added `portfolio_common.market_prices.coerce_positive_market_price_or_none(...)` and reused it in
`ValuationLogic.calculate_valuation(...)` before any currency conversion, bond quote alignment, or
market-value arithmetic runs.

If a required market price is missing, invalid, zero, or negative, valuation now returns `None`.
The existing valuation consumer behavior then marks the valuation job/snapshot as failed rather
than persisting distorted market value and P&L figures.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_market_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common tests/unit/services/calculators/position_valuation_calculator -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/market_prices.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py tests/unit/libs/portfolio-common/test_market_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/market_prices.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py tests/unit/libs/portfolio-common/test_market_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused market-price valuation proof: `17 passed`
2. Affected valuation and portfolio-common packs: `534 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2343 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
valuation read boundary now matches the authoritative ingestion/event market-price positivity
policy.
