# CR-475: Cost-Basis History And Lot Lookup Identifier Normalization

Date: 2026-05-28

## Scope

Cost-calculator repository lookup query shape for transaction history and persisted lot-state
reconciliation.

## Finding

Cost-basis recalculation reads prior transactions by portfolio and security identifier, then
reconciles persisted lot state for BUY and SELL events. Those reads still compared raw
`portfolio_id`, `security_id`, and excluded `transaction_id` values directly.

Padded caller values or historical padded rows could make prior transactions look missing, or could
fail to exclude the in-flight transaction from its own history set. Either case can distort
realized cost, realized gain/loss, remaining open quantity, accrued offset handling, and downstream
portfolio valuation evidence.

For private banking cost-basis calculation, identifier normalization must happen at the repository
read boundary while preserving stored source values and case semantics.

## Change

Updated `CostCalculatorRepository` so:

1. repository-local identifier trimming is centralized through `_normalize_identifier(...)`,
2. `get_transaction_history(...)` trims caller and persisted portfolio/security IDs,
3. `get_transaction_history(...)` trims the excluded transaction ID before applying the exclusion,
4. `update_lot_open_quantities(...)` trims caller and persisted portfolio/security IDs before
   loading lot-state rows for open-quantity reconciliation.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py`
5. `git diff --check`

Results:

1. Focused cost repository proof: `5 passed`
2. Cost-calculator unit pack: `108 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required.
Cost-basis history and lot-state reconciliation now use trim-normalized identifier lookup semantics
at the repository read boundary.
