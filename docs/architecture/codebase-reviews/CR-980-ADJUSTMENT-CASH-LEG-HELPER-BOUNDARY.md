# CR-980: Adjustment Cash-Leg Helper Boundary

Date: 2026-06-05

## Scope

Split auto-generated adjustment cash-leg construction into focused domain helper boundaries without
changing public builder output, eligibility checks, exception messages, generated transaction IDs,
linkage metadata defaults, settlement-date fallback behavior, movement direction, adjustment
reason, or cash amount policy.

## Finding

`_resolve_adjustment_amount_and_direction` mixed BUY, SELL, DIVIDEND, and INTEREST cash movement
policy in one C-ranked resolver, while `build_auto_generated_adjustment_cash_leg` mixed
AUTO_GENERATE eligibility checks, cash-account resolution, cash-instrument resolution, generated
linkage defaults, settlement-date fallback, and `TransactionEvent` assembly in one B-ranked
builder. This made cash-leg generation harder to review as a transaction-domain control path.

## Action

Added focused helpers for adjustment resolver dispatch, BUY/SELL/DIVIDEND/INTEREST amount policy,
net interest resolution, interest movement direction, AUTO_GENERATE eligibility assertion,
cash-account resolution, cash-instrument resolution, generated linkage metadata, and adjustment
cash-leg event assembly.

## Result

`_resolve_adjustment_amount_and_direction` improved from `C (11)` to `A (3)`, and
`build_auto_generated_adjustment_cash_leg` improved from `B (9)` to `A (1)`. All adjustment
cash-leg functions/classes now report A-ranked cyclomatic complexity, and
`adjustment_cash_leg.py` remains A-ranked maintainability at `A (37.29)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py tests\unit\libs\portfolio_common\test_dual_leg_pairing.py -q`
  => 7 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\adjustment_cash_leg.py tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py tests\unit\libs\portfolio_common\test_dual_leg_pairing.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\adjustment_cash_leg.py tests\unit\libs\portfolio_common\test_adjustment_cash_leg.py tests\unit\libs\portfolio_common\test_dual_leg_pairing.py`
  => 3 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\adjustment_cash_leg.py -s`
  => `_resolve_adjustment_amount_and_direction` `A (3)`; `build_auto_generated_adjustment_cash_leg` `A (1)`; all adjustment cash-leg functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\adjustment_cash_leg.py -s`
  => `adjustment_cash_leg.py` `A (37.29)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\adjustment_cash_leg.py`
  => 174 SLOC / 80 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves public cash-leg generation behavior and operator-facing documentation truth.
