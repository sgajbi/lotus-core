# CR-488: Cost-Basis Lot Input Invariants

Date: 2026-05-28

## Scope

FIFO and average-cost basis strategy lot intake.

## Finding

The cost calculator validates BUY quantity and cost outputs before normal strategy execution, and
the disposition engine skips non-positive quantities before delegating lot creation. The underlying
FIFO and average-cost strategies, however, could still be called directly by tests, initialization
paths, or future replay/repair loaders with dirty lot inputs. A mutated BUY lot with negative
quantity or negative cost basis could enter strategy state, distort available quantity, divide cost
by an invalid quantity, and corrupt realized P&L for later sells.

For banking-grade cost-basis calculation, the lot state itself must reject invalid economic inputs
instead of relying only on the caller path.

## Change

Added shared buy-lot input validation for cost-basis strategies.

The FIFO and average-cost strategy lot intake now:

1. requires `net_cost` and `net_cost_local` before lot creation,
2. rejects non-positive lot quantity unless quantity and both costs are all zero,
3. rejects negative base or local cost basis,
4. uses normalized `Decimal` values for lot quantity and cost aggregation,
5. preserves existing zero-quantity/zero-cost no-op behavior.

Added direct strategy tests for dirty post-construction negative BUY quantities and negative BUY
cost basis across both FIFO and average-cost strategies.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_basis_strategies.py tests/unit/services/calculators/cost_calculator_service/engine/test_cost_basis_strategies.py`
5. `make warning-gate`
6. `git diff --check`

Results:

1. Focused cost-basis strategy proof: `14 passed`
2. Cost-calculator unit pack: `115 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Warning gate: `2354 passed`, `9 deselected`, zero warnings
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. Cost
basis strategy state now defends itself against invalid persisted or replayed lot inputs before
they can affect available quantity or realized P&L calculations.
