# CR-1019: Valuation Price Policy Boundary

Date: 2026-06-05

## Scope

Reduce shared valuation price normalization complexity while preserving the existing equity price
behavior, bond unit-price behavior, legacy bond percent-quote scaling thresholds, numeric input
coercion, and required value validation.

## Finding

`resolve_valuation_unit_price` mixed required decimal coercion, product-type normalization, bond
eligibility checks, zero-quantity guard behavior, local average-cost calculation, percent-quote
eligibility, price-ratio calculation, and multiplier selection in one B-ranked helper used by
valuation and reconciliation calculations.

## Action

Added focused helpers for bond percent-quote normalization eligibility, product-type
normalization, percent-quote multiplier selection, legacy percent-quote detection, and ratio-based
multiplier selection. Added a direct regression test for the zero-quantity bond guard.

## Result

`resolve_valuation_unit_price` improved from `B (9)` to `A (2)`. Every function in
`valuation_prices.py` now reports A-ranked cyclomatic complexity. The module remains A-ranked
maintainability at `A (50.48)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_valuation_prices.py -q`
  => 6 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_prices.py tests\unit\libs\portfolio-common\test_valuation_prices.py`
  => all checks passed
- `python -m ruff format src\libs\portfolio-common\portfolio_common\valuation_prices.py tests\unit\libs\portfolio-common\test_valuation_prices.py`
  => 2 files reformatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\valuation_prices.py -s`
  => every function A-ranked by cyclomatic complexity
- `python -m radon mi src\libs\portfolio-common\portfolio_common\valuation_prices.py -s`
  => `valuation_prices.py` `A (50.48)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\valuation_prices.py`
  => 51 SLOC / 29 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared valuation pricing policy refactor
that preserves existing valuation unit-price behavior.
