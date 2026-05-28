# CR-469: Cost FX Lookup Currency Normalization

Date: 2026-05-28

## Scope

Cost-calculator FX-rate lookup query shape for cross-currency transaction cost basis.

## Finding

`CostCalculatorRepository.get_fx_rate(...)` compared raw caller currency values directly against
`fx_rates.from_currency` and `fx_rates.to_currency`. Padded or lower-case caller input, or
historical non-canonical FX rows, could cause cost calculation to treat an available rate as
missing. That can block cost processing or distort transaction cost-basis supportability even
though the platform already owns a normalized functional index for FX pair lookup.

For private banking transaction economics, FX lookup must be deterministic and compatible with the
same normalized reference-data posture used by the read-plane and valuation hardening work.

## Change

Updated the cost-calculator repository so:

1. caller `from_currency` and `to_currency` values are normalized through the shared
   `portfolio_common.currency_codes.normalize_currency_code(...)` helper,
2. persisted FX rows are compared through `upper(trim(...))` predicates that match the existing
   `ix_fx_rates_normalized_pair_rate_date` functional index,
3. repository tests prove padded lower-case input compiles to normalized predicates while
   preserving the as-of date fence and latest-rate ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py -q`
2. `python -m pytest tests/unit/services/calculators/cost_calculator_service -q`
3. `python -m ruff check src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py`
4. `python -m ruff format --check src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_repository.py`
5. `git diff --check`

Results:

1. Focused cost repository proof: `2 passed`
2. Cost-calculator unit pack: `105 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed
5. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The cost
calculator now uses normalized, functional-index-compatible FX lookup semantics for cross-currency
transaction cost basis.
