# CR-975: Interest Transaction Validation Boundary

Date: 2026-06-05

## Scope

Split canonical INTEREST transaction validation into focused domain helper boundaries without
changing public validator output, issue ordering, reason codes, field names, messages, normalized
control code behavior, strict metadata behavior, cash-entry policy behavior, settlement-date
requirements, currency requirements, or net interest reconciliation behavior.

## Finding

`validate_interest_transaction` mixed transaction-type validation, settlement-date presence,
zero quantity/price policy, gross amount policy, interest direction, deduction checks, net interest
reconciliation, currency requirements, date ordering, strict metadata requirements, and cash-entry
mode linkage checks in one D-ranked domain validator. This is a transaction-control path, so the
complexity made the interest validation policy harder to review and extend safely.

## Action

Added focused helpers for transaction-type validation, settlement-date presence, zero
quantity/price policy, gross amount policy, interest direction, nonnegative deductions, net
interest reconciliation, currency fields, date ordering, strict linkage metadata, strict policy
metadata, cash-entry policy, settlement cash-account requirements, and external cash-link
requirements.

## Result

`validate_interest_transaction` improved from `D (29)` to `A (1)`. All INTEREST validation
functions/classes now report A-ranked cyclomatic complexity, and `interest_validation.py` remains
A-ranked maintainability at `A (33.41)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py -q`
  => 27 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\interest_validation.py tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\interest_validation.py tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py tests\unit\libs\portfolio_common\test_transaction_currency_models.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\interest_validation.py -s`
  => `validate_interest_transaction` `A (1)`; all INTEREST validation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\interest_validation.py -s`
  => `interest_validation.py` `A (33.41)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\interest_validation.py`
  => 282 SLOC / 96 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain validator refactor that
preserves public validation contracts, canonical INTEREST transaction semantics, and
operator-facing documentation truth.
