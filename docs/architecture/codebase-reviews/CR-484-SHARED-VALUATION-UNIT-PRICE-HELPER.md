# CR-484: Shared Valuation Unit Price Helper

Date: 2026-05-28

## Scope

Duplicated bond unit-price alignment logic across position valuation and financial reconciliation.

## Finding

Position valuation and financial reconciliation both carried the same bond quote alignment logic for
legacy percent-of-par style prices. That duplication made two calculation surfaces responsible for
the same private-banking valuation policy: the worker persisted valuation snapshots with one copy,
while reconciliation reconstructed expected values with another.

For enterprise-grade calculation reliability, reconciliation should verify the same deterministic
valuation rule used by the calculator rather than maintaining a parallel implementation that can
drift.

## Change

Added `portfolio_common.valuation_prices.resolve_valuation_unit_price(...)` and reused it in:

1. `ValuationLogic.calculate_valuation(...)`,
2. `ReconciliationService._expected_market_value_local(...)`.

The helper preserves current behavior for equities, legacy bond percent quotes, and bond prices
already represented in unit-price terms.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_valuation_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common tests/unit/services/calculators/position_valuation_calculator tests/unit/services/financial_reconciliation_service -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/valuation_prices.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/libs/portfolio-common/test_valuation_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/valuation_prices.py src/services/calculators/position_valuation_calculator/app/logic/valuation_logic.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/libs/portfolio-common/test_valuation_prices.py tests/unit/services/calculators/position_valuation_calculator/logic/test_valuation_logic.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused shared valuation-price proof: `28 passed`
2. Affected valuation, reconciliation, and portfolio-common packs: `556 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2346 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
valuation and reconciliation calculation paths now use one shared unit-price policy.
