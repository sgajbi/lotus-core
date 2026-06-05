# CR-978: Dividend Transaction Validation Boundary

Date: 2026-06-05

## Scope

Split canonical DIVIDEND transaction validation into focused domain helper boundaries without
changing public validator output, issue ordering, reason codes, field names, messages, normalized
control code behavior, strict metadata behavior, cash-entry policy behavior, settlement-date
requirements, currency requirements, or zero quantity/price policy.

## Finding

`validate_dividend_transaction` mixed transaction-type validation, settlement-date presence, zero
quantity and price policy, positive gross-amount policy, currency requirements, date ordering,
strict metadata requirements, and cash-entry mode linkage checks in one D-ranked domain validator.
This is a transaction-control path, so the complexity made the dividend validation policy harder
to review and extend safely.

## Action

Added focused helpers for transaction-type validation, settlement-date presence, zero quantity,
zero price, positive gross amount, currency fields, date ordering, strict linkage metadata, strict
policy metadata, cash-entry policy, auto-generated cash-entry requirements, and upstream-provided
cash-entry requirements.

## Result

`validate_dividend_transaction` improved from `D (21)` to `A (1)`. All DIVIDEND validation
functions/classes now report A-ranked cyclomatic complexity, and `dividend_validation.py` remains
A-ranked maintainability at `A (37.73)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_dividend_validation.py tests\unit\libs\portfolio_common\test_dividend_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py -q`
  => 23 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\dividend_validation.py tests\unit\libs\portfolio_common\test_dividend_validation.py tests\unit\libs\portfolio_common\test_dividend_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\dividend_validation.py tests\unit\libs\portfolio_common\test_dividend_validation.py tests\unit\libs\portfolio_common\test_dividend_linkage.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => 5 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\dividend_validation.py -s`
  => `validate_dividend_transaction` `A (1)`; all DIVIDEND validation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\dividend_validation.py -s`
  => `dividend_validation.py` `A (37.73)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\dividend_validation.py`
  => 214 SLOC / 78 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain validator refactor that
preserves public validation contracts, canonical DIVIDEND transaction semantics, and
operator-facing documentation truth.
