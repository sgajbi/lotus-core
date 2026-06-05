# CR-1021: Transaction Fee Policy Boundary

Date: 2026-06-05

## Scope

Reduce shared transaction fee resolution complexity while preserving explicit trade-fee fallback,
fee-component override behavior, blank component handling, numeric coercion, invalid value
rejection, and non-negative amount validation.

## Finding

`resolve_transaction_trade_fee` mixed explicit fee normalization, explicit fee validation,
component-presence detection, per-component normalization, negative component validation,
component collection, and total calculation in one B-ranked shared event helper.

## Action

Added focused helpers for optional fee validation, fee-component presence detection, component
totaling, component validation, and shared non-negative amount enforcement. Added a direct
regression test for negative explicit `trade_fee` values.

## Result

`resolve_transaction_trade_fee` improved from `B (7)` to `A (2)`. Every function in
`transaction_fee_components.py` now reports A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (47.90)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_transaction_fee_components.py -q`
  => 5 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_fee_components.py tests\unit\libs\portfolio-common\test_transaction_fee_components.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\transaction_fee_components.py tests\unit\libs\portfolio-common\test_transaction_fee_components.py`
  => 2 files reformatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_fee_components.py -s`
  => `resolve_transaction_trade_fee` `A (2)` and every function A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_fee_components.py -s`
  => `transaction_fee_components.py` `A (47.90)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_fee_components.py`
  => 54 SLOC / 42 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared transaction event fee-policy
refactor that preserves existing fee resolution semantics.
