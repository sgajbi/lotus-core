# CR-974: FX Transaction Validation Boundary

Date: 2026-06-05

## Scope

Split canonical FX transaction validation into focused domain helper boundaries without changing
public validator output, issue ordering, reason codes, field names, messages, normalized control
code behavior, strict metadata behavior, cash-leg linkage checks, contract-id checks, swap-group
checks, optional policy-mode checks, or realized P&L identity checks.

## Finding

`validate_fx_transaction` mixed control-code validation, component identity checks, zero
quantity/price checks, date ordering, currency-pair checks, quote convention checks, positive
amount/rate checks, strict metadata checks, cash-settlement checks, contract checks, swap-group
checks, optional policy-mode checks, and realized P&L checks in one E-ranked domain validator.
This is a private-banking transaction-control path, so high complexity made the validation policy
harder to review and extend safely.

## Action

Added focused helpers for normalized FX control codes, control-code validation, component identity,
zero quantity/price policy, settlement-date policy, currency-pair policy, quote convention policy,
positive amount/rate policy, strict linkage metadata, strict policy metadata, cash-settlement
components, contract identifiers, swap structure, optional policy modes, and realized P&L fields.

## Result

`validate_fx_transaction` improved from `E (37)` to `A (1)`. All FX validation functions/classes
now report A-ranked cyclomatic complexity, and `fx_validation.py` remains A-ranked
maintainability at `A (27.02)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py -q`
  => 22 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py -s`
  => `validate_fx_transaction` `A (1)`; all FX validation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py -s`
  => `fx_validation.py` `A (27.02)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\fx_validation.py`
  => 408 SLOC / 137 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain validator refactor that
preserves public validation contracts, canonical FX transaction semantics, and operator-facing
documentation truth.
