# CR-979: CA Bundle A Transaction Validation Boundary

Date: 2026-06-05

## Scope

Split CA Bundle A transaction validation into focused domain helper boundaries without changing
public validator output, early invalid-type return behavior, issue ordering, reason codes, field
names, messages, transaction-type normalization, source/target instrument requirements, or
cash-consideration link policy.

## Finding

`validate_ca_bundle_a_transaction` mixed transaction-type classification, parent event reference
checks, linkage identifier checks, source instrument requirements, target instrument requirements,
and cash-consideration link presence/consistency checks in one D-ranked domain validator. This is a
corporate-action transaction-control path, so the complexity made Bundle A policy harder to review
and extend safely.

## Action

Added focused helpers for transaction-type validation, parent event reference validation, linkage
identifier validation, source instrument validation, target instrument validation, cash
consideration link orchestration, cash-link presence, and cash-link consistency.

## Result

`validate_ca_bundle_a_transaction` improved from `D (22)` to `A (2)`. All CA Bundle A validation
functions/classes now report A-ranked cyclomatic complexity, and `ca_bundle_a_validation.py`
remains A-ranked maintainability at `A (38.16)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py -q`
  => 14 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_validation.py -s`
  => `validate_ca_bundle_a_transaction` `A (2)`; all CA Bundle A validation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_validation.py -s`
  => `ca_bundle_a_validation.py` `A (38.16)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_validation.py`
  => 171 SLOC / 68 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain validator refactor that
preserves public validation contracts, CA Bundle A transaction semantics, and operator-facing
documentation truth.
