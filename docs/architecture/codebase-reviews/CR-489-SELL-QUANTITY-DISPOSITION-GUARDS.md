# CR-489: Sell Quantity Disposition Guards

Date: 2026-05-28

## Scope

Cost-calculator SELL handling and cost-basis strategy disposition quantity handling.

## Finding

The transaction model normally prevents negative quantities, but dirty in-memory objects,
repair/replay payloads, or direct strategy calls can bypass model-construction validation. The SELL
strategy did not reject non-positive quantity before asking the disposition engine for available
quantity and consumption. The average-cost strategy also accepted a negative sell quantity at the
stateful strategy layer, which could increase holdings while returning distorted cost-of-goods-sold
values before the caller detected an invalid consumed quantity.

For banking-grade realized P&L, invalid disposal quantities must be rejected before state mutation.

## Change

Hardened sell/disposition quantity handling:

1. `SellStrategy` now rejects non-positive transaction quantity before any available-quantity or
   lot-consumption call.
2. FIFO and average-cost strategies now reject negative direct sell quantities before state
   mutation.
3. Strategy-level zero-quantity sell requests remain a no-op for existing property-test semantics.
4. Added direct strategy proof that negative sell quantities return an error without changing
   available quantity.
5. Added cost-calculator proof that dirty negative SELL quantity is rejected before disposition
   engine access.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused strategy/calculator proof: `64 passed`
2. Cost-calculator unit pack: `118 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2357 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. SELL and
disposition paths now reject invalid dirty quantities before they can alter cost-basis state or
distort realized P&L.
