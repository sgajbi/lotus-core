# CR-977: Buy Transaction Validation Boundary

Date: 2026-06-05

## Scope

Split canonical BUY transaction validation into focused domain helper boundaries without changing
public validator output, issue ordering, reason codes, field names, messages, normalized control
code behavior, strict metadata behavior, settlement-date requirements, currency requirements, or
positive quantity and gross-amount policy.

## Finding

`validate_buy_transaction` mixed transaction-type validation, settlement-date presence, positive
quantity policy, positive gross-amount policy, currency requirements, date ordering, and strict
metadata requirements in one C-ranked domain validator. This is a transaction-control path, so the
complexity made the buy validation policy harder to review and extend safely.

## Action

Added focused helpers for transaction-type validation, settlement-date presence, positive quantity,
positive gross amount, currency fields, date ordering, strict linkage metadata, and strict policy
metadata.

## Result

`validate_buy_transaction` improved from `C (14)` to `A (1)`. All BUY validation
functions/classes now report A-ranked cyclomatic complexity, and `buy_validation.py` remains
A-ranked maintainability at `A (42.80)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py -q`
  => 19 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\buy_validation.py tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\buy_validation.py tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => 5 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\buy_validation.py -s`
  => `validate_buy_transaction` `A (1)`; all BUY validation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\buy_validation.py -s`
  => `buy_validation.py` `A (42.80)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\buy_validation.py`
  => 146 SLOC / 59 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain validator refactor that
preserves public validation contracts, canonical BUY transaction semantics, and operator-facing
documentation truth.
