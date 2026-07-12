# CR-1033: Cost Consumer Fee Transform Boundary

Date: 2026-06-05

## Scope

Reduce cost calculator consumer event-to-engine transformation complexity while preserving fee
normalization, negative-fee rejection, explicit fee-component handling, legacy positive
`trade_fee` handling, zero-fee handling, and cost-engine payload shape.

## Finding

`CostCalculatorConsumer._transform_event_for_engine` still mixed event serialization, fee-field
removal, component normalization, trade-fee resolution, explicit component payload construction,
legacy brokerage fallback, and zero-fee payload construction in one B-ranked helper.

## Action

Extracted focused helpers for fee-component removal, explicit component detection, component
normalization, and engine fee-field application. Added a direct boundary test that pins the legacy
positive `trade_fee` path to the expected brokerage fee payload.

## Result

`CostCalculatorConsumer._transform_event_for_engine` improved from `B (9)` to `A (2)`. The cost
consumer module remains A-ranked maintainability at `A (22.19)`, and the remaining B-ranked
consumer helpers are now limited to reconciliation/upstream cash-leg validation and cost-engine
event construction.

## Evidence

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q`
  => 27 passed
- `python -m ruff check src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => 2 files reformatted
- `python -m radon cc src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `CostCalculatorConsumer._transform_event_for_engine` `A (2)`
- `python -m radon mi src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `consumer.py` `A (22.19)`
- `python -m radon raw src\services\calculators\cost_calculator_service\app\consumer.py`
  => 671 SLOC / 317 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cost calculator consumer refactor that
preserves existing fee transformation and cost-engine payload semantics.
