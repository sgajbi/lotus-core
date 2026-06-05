# CR-981: Upstream Cash-Leg Pairing Validation Boundary

Date: 2026-06-05

## Scope

Split upstream-provided cash-leg pairing validation into focused domain helper boundaries without
changing public validator output, issue ordering, field names, messages, product-leg cash-entry
mode policy, portfolio matching, external cash transaction matching, ADJUSTMENT cash-leg policy,
positive cash amount policy, or shared linkage metadata checks.

## Finding

`validate_upstream_cash_leg_pairing` mixed cash-entry mode validation, portfolio matching,
external cash transaction matching, cash-leg transaction-type validation, amount validation,
economic-event matching, and linked-transaction-group matching in one C-ranked function. This made
the dual-leg cash pairing contract harder to review as a reusable transaction-domain guardrail.

## Action

Added focused helpers for product-leg cash-entry mode, portfolio matching, external cash
transaction ID matching, cash-leg transaction type, cash-leg gross amount, economic event ID, and
linked transaction group ID.

## Result

`validate_upstream_cash_leg_pairing` improved from `C (12)` to `A (1)`. All dual-leg pairing
functions/classes now report A-ranked cyclomatic complexity, and `dual_leg_pairing.py` remains
A-ranked maintainability at `A (56.95)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_dual_leg_pairing.py tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\dual_leg_pairing.py tests\unit\libs\portfolio_common\test_dual_leg_pairing.py tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\dual_leg_pairing.py tests\unit\libs\portfolio_common\test_dual_leg_pairing.py tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py`
  => 3 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\dual_leg_pairing.py -s`
  => `validate_upstream_cash_leg_pairing` `A (1)`; all dual-leg pairing functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\dual_leg_pairing.py -s`
  => `dual_leg_pairing.py` `A (56.95)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\dual_leg_pairing.py`
  => 126 SLOC / 54 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain guardrail refactor that
preserves public cash-leg pairing behavior and operator-facing documentation truth.
