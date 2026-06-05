# CR-989: CA Bundle A Reconciliation Helper Boundary

Date: 2026-06-05

## Scope

Split CA Bundle A reconciliation into focused domain helper boundaries without changing source-leg
counting, target-leg counting, cash-consideration counting, source basis calculation, target basis
calculation, net basis delta calculation, basis tolerance behavior, reconciliation statuses, or
dependency gap detection.

## Finding

`evaluate_ca_bundle_a_reconciliation` mixed event iteration, transaction-type classification,
source/target/cash leg accumulation, net basis delta calculation, status resolution, and result
assembly in one B-ranked helper. This made corporate-action Bundle A reconciliation harder to
review as a transaction-domain control path.

## Action

Added a focused reconciliation accumulator plus helpers for event accumulation, source-leg
accumulation, target-leg accumulation, and reconciliation status resolution.

## Result

`evaluate_ca_bundle_a_reconciliation` improved from `B (8)` to `A (2)`. All CA Bundle A
reconciliation functions/classes now report A-ranked cyclomatic complexity, and
`ca_bundle_a_reconciliation.py` remains A-ranked maintainability at `A (39.54)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py -q`
  => 14 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_reconciliation.py -s`
  => `evaluate_ca_bundle_a_reconciliation` `A (2)`; all CA Bundle A reconciliation functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_reconciliation.py -s`
  => `ca_bundle_a_reconciliation.py` `A (39.54)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\ca_bundle_a_reconciliation.py`
  => 105 SLOC / 79 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves CA Bundle A reconciliation behavior and operator-facing documentation truth.
