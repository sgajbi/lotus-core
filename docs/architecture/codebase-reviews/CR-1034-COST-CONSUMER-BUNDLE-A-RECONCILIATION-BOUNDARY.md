# CR-1034: Cost Consumer Bundle A Reconciliation Boundary

Date: 2026-06-05

## Scope

Reduce cost calculator consumer Bundle A reconciliation diagnostics complexity while preserving
Corporate Action Bundle A eligibility checks, linked-group/parent-reference requirements,
duplicate group suppression, group transaction loading, reconciliation evaluation, missing
dependency detection, and diagnostic logging.

## Finding

`CostCalculatorConsumer._record_bundle_a_reconciliation_diagnostics` mixed Bundle A eligibility,
group key extraction, duplicate suppression, repository reads, event validation, reconciliation
evaluation, missing dependency detection, logging, and processed-key mutation in one B-ranked
helper.

## Action

Extracted focused helpers for reconciliation-key resolution, complete key validation, Bundle A group
event loading, and missing dependency calculation. Added a direct guard test proving non-Bundle-A
events do not produce a reconciliation key even when linked-group fields are present.

## Result

`CostCalculatorConsumer._record_bundle_a_reconciliation_diagnostics` improved from `B (9)` to
`A (3)`. The cost consumer module remains A-ranked maintainability at `A (20.93)`, and the only
remaining B-ranked helpers in the module are upstream cash-leg validation and cost-engine event
construction.

## Evidence

- `python -m pytest tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py -q`
  => 28 passed
- `python -m ruff check src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => all checks passed
- `python -m ruff format src\services\calculators\cost_calculator_service\app\consumer.py tests\unit\services\calculators\cost_calculator_service\consumer\test_cost_calculator_consumer.py`
  => 1 file reformatted, 1 file left unchanged
- `python -m radon cc src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `CostCalculatorConsumer._record_bundle_a_reconciliation_diagnostics` `A (3)`
- `python -m radon mi src\services\calculators\cost_calculator_service\app\consumer.py -s`
  => `consumer.py` `A (20.93)`
- `python -m radon raw src\services\calculators\cost_calculator_service\app\consumer.py`
  => 709 SLOC / 330 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal cost calculator consumer refactor that
preserves existing Bundle A reconciliation diagnostic behavior.
